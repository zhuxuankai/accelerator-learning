# -*- coding: utf-8 -*-
"""每周维护：增量入库 -> 覆盖度 -> 看板 -> 下周计划草稿 -> Agent 摘要

幂等：同一周重复运行不会重复生成计划文件。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    KB,
    PY,
    ROADMAP,
    WS,
    connect_db,
    load_config,
    now_iso,
    read_json,
)
from dashboard import render_dashboard  # noqa: E402

PROGRESS_CSV = ROADMAP / "进度追踪.csv"
PLAN_DIR = ROADMAP / "周计划"
COVERAGE_MD = ROADMAP / "覆盖度.md"
DASHBOARD = ROADMAP / "dashboard.html"
READING_LIST = KB / "papers" / "阅读清单.md"

def course_names() -> list[str]:
    """课程列表从 kb/config.json 的 include_dirs 读取（排除论文目录）。"""
    try:
        cfg = load_config()
    except SystemExit:
        return []
    return [name for name in cfg.get("include_dirs", []) if name != "文献"]


def run_ingest() -> str:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [str(PY), str(Path(__file__).resolve().parent / "ingest.py")],
        capture_output=True,
        env=env,
    )
    return proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")


def db_stats() -> dict:
    conn = connect_db(readonly=True)
    try:
        docs = [
            dict(r)
            for r in conn.execute(
                "SELECT rel_path, title, course, kind, n_units, n_chunks, ocr_ratio,"
                " status, version_rank, is_latest FROM docs"
            )
        ]
        total_chunks = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
    finally:
        conn.close()
    by_course: dict[str, dict] = {}
    for d in docs:
        info = by_course.setdefault(
            d["course"], {"docs": 0, "units": 0, "chunks": 0, "ocr_units": 0, "latest_docs": 0}
        )
        info["docs"] += 1
        info["units"] += d["n_units"] or 0
        info["chunks"] += d["n_chunks"] or 0
        info["ocr_units"] += round((d["ocr_ratio"] or 0) * (d["n_units"] or 0))
        if d["is_latest"]:
            info["latest_docs"] += 1
    return {"docs": docs, "by_course": by_course, "total_chunks": total_chunks}


def read_progress() -> list[dict]:
    if not PROGRESS_CSV.exists():
        return []
    rows = []
    with PROGRESS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append({k: (v or "").strip() for k, v in row.items() if k})
    return rows


def assigned_papers() -> set[str]:
    """已经出现在历史周计划里的论文，避免重复推荐。"""
    used: set[str] = set()
    if not PLAN_DIR.exists():
        return used
    for path in PLAN_DIR.glob("*.md"):
        for match in re.finditer(r"`(文献/[^`]+)`", path.read_text(encoding="utf-8")):
            used.add(match.group(1))
    return used


def pick_papers(limit: int = 4) -> list[dict]:
    """选本周要读的论文：先组内高引，再最老的经典，其余按引用补足。"""
    meta_path = KB / "papers" / "metadata.jsonl"
    if not meta_path.exists():
        return []
    pool = []
    for line in meta_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pool.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    used = assigned_papers()
    fresh = [p for p in pool if p.get("local_pdf") and p["local_pdf"] not in used]
    if not fresh:
        fresh = [p for p in pool if p.get("local_pdf")]
    classics = [p for p in fresh if p.get("source") == "classic"]
    group = [p for p in fresh if p.get("source") != "classic"]

    picks: list[dict] = []
    if group:
        picks.append(max(group, key=lambda p: p.get("cited_by", 0)))
    if classics:
        picks.append(min(classics, key=lambda p: p.get("year", 9999)))
    for paper in sorted(fresh, key=lambda p: -p.get("cited_by", 0)):
        if paper in picks:
            continue
        picks.append(paper)
        if len(picks) >= limit:
            break
    return picks[:limit]


def next_monday(today: dt.date) -> dt.date:
    return today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)


def this_monday(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=today.weekday())


def plan_path(monday: dt.date) -> Path:
    return PLAN_DIR / f"{monday.isoformat()}.md"


def write_coverage(stats: dict, progress: list[dict]) -> None:
    lines = ["# 覆盖度报告", "", f"生成时间：{now_iso()}", "", "## 语料规模", ""]
    lines.append("| 目录 | 文档数 | 最新版 | 单元(页/张) | 索引块 | OCR 单元 |")
    lines.append("|---|---|---|---|---|---|")
    for course, info in sorted(stats["by_course"].items()):
        lines.append(
            f"| {course} | {info['docs']} | {info['latest_docs']} | {info['units']} | "
            f"{info['chunks']} | {info['ocr_units']} |"
        )
    lines += ["", f"索引块总数：{stats['total_chunks']}", "", "## 进度项", ""]
    if not progress:
        lines.append("（进度追踪.csv 为空）")
    else:
        counts: dict[str, int] = {}
        for row in progress:
            key = row.get("状态", "未填") or "未填"
            counts[key] = counts.get(key, 0) + 1
        lines += ["| 状态 | 条数 |", "|---|---|"]
        for status, n in sorted(counts.items()):
            lines.append(f"| {status} | {n} |")
        inferred = [r for r in progress if r.get("来源") == "推断"]
        lines += ["", f"其中标记为「推断」、需要你确认的有 {len(inferred)} 项。"]
    COVERAGE_MD.write_text("\n".join(lines), encoding="utf-8")


def write_plan(monday: dt.date, stats: dict, progress: list[dict]) -> Path:
    """确保指定周（该周的周一）有一份计划；已存在则原样返回。"""
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    path = plan_path(monday)
    if path.exists():
        return path
    is_next = monday > this_monday(dt.date.today())
    heading = "下周计划" if is_next else "本周计划"
    week_no = monday.isocalendar()[1]
    done = [r for r in progress if r.get("状态") == "已完成"]
    doing = [r for r in progress if r.get("状态") == "进行中"]
    inferred = [r for r in progress if r.get("来源") == "推断"]
    papers = pick_papers(4)
    lines = [
        f"# {heading} {monday.isoformat()}（第 {week_no} 周）",
        "",
        f"生成时间：{now_iso()}",
        "",
        "## 上周复盘（待填）" if is_next else "## 本周进度（待回填）",
        "",
        f"- 已完成项：{'、'.join(r.get('名称', '') for r in done[-5:]) or '（待回填）'}",
        f"- 进行中：{'、'.join(r.get('名称', '') for r in doing) or '（无）'}",
        "",
        "## 任务清单" if not is_next else "## 本周任务",
        "",
        "### 论文",
        "",
    ]
    if papers:
        def label(paper: dict) -> str:
            tag = "组内" if paper.get("source") != "classic" else "经典"
            return (
                f"[{tag}] {paper['title']}（{paper.get('journal') or 'preprint'}，"
                f"{paper.get('year')}，引用 {paper.get('cited_by', 0)}）`{paper['local_pdf']}`"
            )

        for i, item in enumerate(papers[:2], 1):
            lines.append(f"- [ ] 精读 {i}：{label(item)}")
        for item in papers[2:4]:
            lines.append(f"- [ ] 泛读：{label(item)}")
    else:
        lines.append("- [ ] 论文语料尚未下载：先跑 `run.ps1 papers` 并确认候选清单")
    lines += ["", "### 仿真", "", "- [ ] （按阶段填写：ELEGANT / SRW / GENESIS）", "", "### 课程复习", ""]
    lines += [f"- [ ] {course}：" for course in course_names()]
    lines += ["", "### 写作/汇报", "", "- [ ] ", "", "## 需要你确认的进度项（系统只做推断，不自动打勾）", ""]
    if inferred:
        lines += [
            f"- {r.get('类型', '')}｜{r.get('名称', '')}（{r.get('关联课程', '')}）" for r in inferred[:10]
        ]
    else:
        lines.append("- （无）")
    lines += [
        "",
        "## 语料与索引",
        "",
        f"- 索引块：{stats['total_chunks']}；变化见 `学习路线/覆盖度.md`",
        "- 有新课件时丢进对应课程目录，跑 `run.ps1 ingest` 增量入库",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ingest", action="store_true")
    ap.add_argument("--show", action="store_true", help="只打印本周任务清单，不做任何维护动作")
    args = ap.parse_args()
    load_config()

    if args.show:
        monday = this_monday(dt.date.today())
        path = plan_path(monday)
        if not path.exists():
            stats = db_stats()
            progress = read_progress()
            path = write_plan(monday, stats, progress)
        print(f"# 本周计划文件：{path.relative_to(WS)}")
        print()
        print(path.read_text(encoding="utf-8"))
        return

    ingest_log = "" if args.no_ingest else run_ingest()
    manifest = read_json(KB / "manifest.json", {"files": {}})
    cutoff = (dt.datetime.now() - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    new_files = [
        rel
        for rel, info in manifest.get("files", {}).items()
        if (info.get("last_indexed") or "") >= cutoff
    ]
    stats = db_stats()
    progress = read_progress()
    write_coverage(stats, progress)
    DASHBOARD.write_text(render_dashboard(stats, progress, new_files, now_iso()), encoding="utf-8")
    today = dt.date.today()
    plan_this = write_plan(this_monday(today), stats, progress)
    plan_next = write_plan(next_monday(today), stats, progress)

    today_iso = dt.date.today().isoformat()
    overdue = [
        r
        for r in progress
        if r.get("状态") != "已完成"
        and re.match(r"\d{4}-\d{2}-\d{2}", r.get("计划完成") or "")
        and r["计划完成"] < today_iso
    ]
    inferred = [r for r in progress if r.get("来源") == "推断"]

    print("=== 每周维护摘要 ===")
    print(f"时间：{now_iso()}")
    if ingest_log.strip():
        tail = [ln for ln in ingest_log.strip().splitlines() if ln.strip()]
        print("入库：" + " / ".join(tail[-2:]))
    print(f"索引块总数：{stats['total_chunks']}；文档数：{len(stats['docs'])}")
    print(f"本周任务清单：{plan_this.relative_to(WS)}")
    print(f"下周计划：    {plan_next.relative_to(WS)}")
    print(f"逾期任务：{len(overdue)}　待确认进度项：{len(inferred)}")
    for row in overdue[:5]:
        print(f"  - 逾期：{row.get('名称', '')}（计划 {row.get('计划完成')}）")
    for row in inferred[:5]:
        print(f"  - 待确认：{row.get('名称', '')}")
    notify = bool(new_files or overdue or inferred)
    print("是否通知用户：" + ("是（有变化或待办）" if notify else "否（无变化）"))


if __name__ == "__main__":
    main()
