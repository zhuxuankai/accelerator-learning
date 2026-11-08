from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import CockpitError, Paths, load_config
from .extract import discover_files

PROGRESS_FIELDS = [
    "id",
    "类型",
    "名称",
    "关联课程",
    "计划完成",
    "状态",
    "来源",
    "证据",
    "更新日期",
    "备注",
]
READING_FIELDS = [
    "id",
    "rel_path",
    "title",
    "category",
    "status",
    "source",
    "evidence",
    "last_planned",
    "完成日期",
]


def _read_csv(path: Path, fields: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [{field: (row.get(field) or "").strip() for field in fields} for row in rows]


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    temporary.replace(path)


def _stable_id(prefix: str, value: str) -> str:
    return prefix + "-" + hashlib.sha1(value.encode()).hexdigest()[:10]


def list_progress(root: Path) -> list[dict[str, str]]:
    return _read_csv(Paths.for_root(root).progress_csv, PROGRESS_FIELDS)


def suggest_progress(root: Path, *, accept: bool = False) -> list[dict[str, str]]:
    cfg, _, _ = load_config(root)
    paths = Paths.for_root(root)
    existing = list_progress(root)
    known = {row["名称"] for row in existing}
    suggestions = []
    for path in discover_files(Path(root).resolve(), cfg):
        rel_path = path.relative_to(Path(root).resolve()).as_posix()
        name = f"学习 {path.stem}"
        if path.stem in known or name in known:
            continue
        suggestions.append(
            {
                "id": _stable_id("prog", rel_path),
                "类型": "课程章节",
                "名称": name,
                "关联课程": Path(rel_path).parts[0],
                "计划完成": "",
                "状态": "未开始",
                "来源": "推断",
                "证据": f"发现课件：{rel_path}",
                "更新日期": date.today().isoformat(),
                "备注": "需用户确认后才算正式学习记录。",
            }
        )
    if accept and suggestions:
        _write_csv(paths.progress_csv, PROGRESS_FIELDS, [*existing, *suggestions])
    return suggestions


def confirm_progress(root: Path, item_id: str, evidence: str) -> dict[str, str]:
    if not evidence.strip():
        raise CockpitError("progress confirm 必须用 --evidence 提供作业、代码、笔记或用户明确确认。")
    paths = Paths.for_root(root)
    rows = list_progress(root)
    for row in rows:
        if row["id"] == item_id:
            row["状态"] = "已完成"
            row["来源"] = "已确认"
            row["证据"] = evidence.strip()
            row["更新日期"] = date.today().isoformat()
            _write_csv(paths.progress_csv, PROGRESS_FIELDS, rows)
            return row
    raise CockpitError(f"找不到进度项：{item_id}")


def reject_progress(root: Path, item_id: str) -> dict[str, str]:
    paths = Paths.for_root(root)
    rows = list_progress(root)
    for row in rows:
        if row["id"] == item_id:
            row["状态"] = "已忽略"
            row["更新日期"] = date.today().isoformat()
            _write_csv(paths.progress_csv, PROGRESS_FIELDS, rows)
            return row
    raise CockpitError(f"找不到进度项：{item_id}")


def import_legacy_progress(root: Path, *, accept: bool = False) -> dict[str, Any]:
    paths = Paths.for_root(root)
    legacy_path = paths.roadmap_dir / "进度追踪.csv"
    if not legacy_path.exists():
        raise CockpitError(f"找不到旧版进度文件：{legacy_path}")
    with legacy_path.open("r", encoding="utf-8-sig", newline="") as handle:
        legacy_rows = list(csv.DictReader(handle))
    existing = list_progress(root)
    by_id = {row["id"]: row for row in existing}
    imported = []
    skipped = 0
    for raw in legacy_rows:
        name = (raw.get("名称") or "").strip()
        if not name:
            continue
        row_id = _stable_id(
            "prog",
            "|".join(
                [
                    (raw.get("关联课程") or "").strip(),
                    name,
                    (raw.get("类型") or "").strip(),
                ]
            ),
        )
        if row_id in by_id:
            skipped += 1
            continue
        original_status = (raw.get("状态") or "未开始").strip()
        safe_status = "待确认" if original_status in {"已完成", "完成"} else original_status
        original_source = (raw.get("来源") or "").strip()
        row = {
            "id": row_id,
            "类型": (raw.get("类型") or "").strip(),
            "名称": name,
            "关联课程": (raw.get("关联课程") or "").strip(),
            "计划完成": (raw.get("计划完成") or "").strip(),
            "状态": safe_status,
            "来源": "推断",
            "证据": (
                f"旧版进度导入；原状态={original_status or '未填'}；"
                f"原来源={original_source or '未填'}；需重新确认"
            ),
            "更新日期": date.today().isoformat(),
            "备注": (raw.get("备注") or "").strip(),
        }
        imported.append(row)
        by_id[row_id] = row
    if accept and imported:
        _write_csv(paths.progress_csv, PROGRESS_FIELDS, [*existing, *imported])
    return {
        "status": "imported" if accept else "dry_run",
        "source": str(legacy_path),
        "target": str(paths.progress_csv),
        "imported_count": 0 if not accept else len(imported),
        "candidate_count": len(imported),
        "skipped_existing": skipped,
        "rows": imported,
    }


def _paper_category(metadata: dict[str, Any]) -> str:
    source = str(metadata.get("source") or "").lower()
    title = str(metadata.get("title") or "").lower()
    if source == "review" or "review" in title or "tutorial" in title:
        return "review"
    if source == "classic":
        return "classic"
    return "group"


def sync_reading(root: Path) -> list[dict[str, str]]:
    paths = Paths.for_root(root)
    rows = _read_csv(paths.reading_csv, READING_FIELDS)
    known = {row["rel_path"] for row in rows}
    metadata_path = root / "kb" / "papers" / "metadata.jsonl"
    if metadata_path.exists():
        for number, line in enumerate(metadata_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                paper = json.loads(line)
            except json.JSONDecodeError:
                continue
            rel_path = str(paper.get("local_pdf") or "").replace("\\", "/")
            if not rel_path or rel_path in known:
                continue
            rows.append(
                {
                    "id": _stable_id("paper", rel_path),
                    "rel_path": rel_path,
                    "title": str(paper.get("title") or Path(rel_path).stem),
                    "category": _paper_category(paper),
                    "status": "unread",
                    "source": "推断",
                    "evidence": "论文文件存在，但尚无用户确认的阅读记录。",
                    "last_planned": "",
                    "完成日期": "",
                }
            )
    if rows:
        _write_csv(paths.reading_csv, READING_FIELDS, rows)
    return rows


def list_reading(root: Path) -> list[dict[str, str]]:
    return _read_csv(Paths.for_root(root).reading_csv, READING_FIELDS)


def confirm_reading(root: Path, item_id: str, evidence: str) -> dict[str, str]:
    if not evidence.strip():
        raise CockpitError("确认阅读必须用 --evidence 提供笔记、汇报或用户明确确认。")
    rows = sync_reading(root)
    for row in rows:
        if row["id"] == item_id:
            row["status"] = "done"
            row["source"] = "confirmed"
            row["evidence"] = evidence.strip()
            row["完成日期"] = date.today().isoformat()
            _write_csv(Paths.for_root(root).reading_csv, READING_FIELDS, rows)
            return row
    raise CockpitError(f"找不到阅读项：{item_id}")


def _load_roadmap(paths: Paths) -> dict[str, Any]:
    candidates = [paths.roadmap_dir / "roadmap.json", paths.roadmap_dir / "roadmap.example.json"]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CockpitError(f"学习路线 JSON 无效：{path}: {exc}") from exc
    raise CockpitError("缺少 学习路线/roadmap.json 或 roadmap.example.json。")


def _current_stage(roadmap: dict[str, Any], today: date) -> dict[str, Any]:
    for stage in roadmap.get("stages", []):
        start = date.fromisoformat(stage["start"])
        end = date.fromisoformat(stage["end"])
        if start <= today <= end:
            return stage
    stages = roadmap.get("stages", [])
    if not stages:
        raise CockpitError("roadmap.json 没有 stages。")
    return stages[-1]


def _pick_papers(root: Path, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows = sync_reading(root)
    by_category: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row["status"] != "done":
            by_category.setdefault(row["category"], []).append(row)
    selections = []
    for slot in cfg.get("reading", {}).get("slots", []):
        category = str(slot.get("category", "group"))
        candidates = by_category.get(category, [])
        if not candidates and category == "group":
            candidates = by_category.get("classic", [])
        candidates.sort(key=lambda row: (row["last_planned"] != "", row["rel_path"]))
        if candidates:
            item = dict(candidates[0])
            item["mode"] = str(slot.get("mode", "泛读"))
            selections.append(item)
    return selections


def _review_candidates(root: Path, cfg: dict[str, Any]) -> list[dict[str, str]]:
    limit = int(cfg.get("weekly", {}).get("max_review_candidates", 1))
    rows = [row for row in list_progress(root) if row["状态"] not in {"已完成", "已忽略"}]
    today = date.today()

    def priority(row: dict[str, str]) -> tuple[int, str]:
        plan = row.get("计划完成", "")
        overdue = bool(plan and plan < today.isoformat())
        active = row.get("状态") == "进行中"
        return (0 if overdue else 1 if active else 2, plan or "9999-12-31")

    return sorted(rows, key=priority)[:limit]


def _write_dashboard(paths: Paths, payload: dict[str, Any]) -> str:
    path = paths.roadmap_dir / "dashboard.html"
    papers = "".join(
        f"<li><b>{item['mode']}</b>：{item['title']}<br><code>{item['rel_path']}</code></li>"
        for item in payload["papers"]
    ) or "<li>本周不安排论文。</li>"
    reviews = "".join(
        f"<li>{item['名称']}（{item['关联课程']}）</li>" for item in payload["reviews"]
    ) or "<li>无法判断</li>"
    html = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><title>加速器学习驾驶舱 v2</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;line-height:1.6}}
code{{background:#f3f3f3;padding:.1rem .3rem}}section{{margin:2rem 0}}</style>
<h1>加速器学习驾驶舱 v2</h1><p>生成时间：{payload['generated_at']}</p>
<section><h2>论文</h2><ul>{papers}</ul></section>
<section><h2>建议复习点</h2><ul>{reviews}</ul></section>
<section><h2>关键词法与向量混合检索</h2><p>本页只展示计划与索引状态，不把“计划出现”当作“已读”。</p></section>
</html>"""
    path.write_text(html, encoding="utf-8")
    return str(path.relative_to(paths.root))


def generate_weekly(
    root: Path,
    *,
    eval_result: dict[str, Any] | None,
    eval_error: str | None = None,
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    cfg, _, _ = load_config(root)
    paths = Paths.for_root(root)
    today = date.today()
    next_monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    plan_dir = paths.roadmap_dir / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    json_path = plan_dir / f"{next_monday.isoformat()}.json"
    markdown_path = plan_dir / f"{next_monday.isoformat()}.md"
    if json_path.exists() and markdown_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        payload["eval"] = eval_result
        payload["eval_error"] = eval_error
        payload["quality"] = quality
        payload["plan"] = str(markdown_path.relative_to(root))
        payload["dashboard"] = str((paths.roadmap_dir / "dashboard.html").relative_to(root))
        return payload

    roadmap = _load_roadmap(paths)
    stage = _current_stage(roadmap, next_monday)
    papers = _pick_papers(root, cfg)
    reviews = _review_candidates(root, cfg)
    simulation = next(
        (
            task
            for task in stage.get("simulation_tasks", [])
            if task.get("status", "未开始") not in {"已完成", "已忽略"}
        ),
        None,
    )
    payload = {
        "week": next_monday.isoformat(),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "stage": {
            "id": stage.get("id"),
            "name": stage.get("name"),
        },
        "papers": papers,
        "reviews": reviews,
        "simulation": simulation,
        "eval": eval_result,
        "eval_error": eval_error,
        "quality": quality,
    }

    paper_lines = [
        f"- [ ] **{item['mode']}**：{item['title']} (`{item['rel_path']}`)"
        for item in papers
    ] or ["- 本周不安排论文；文献语料或未读论文不足。"]
    review_lines = [
        f"- {item['名称']}（{item['关联课程']}，状态：{item['状态']}）"
        for item in reviews
    ] or ["- 无法判断：当前没有可依据的进度记录。"]
    simulation_line = (
        f"- [ ] {simulation.get('title')}：{simulation.get('instructions', '')}"
        if simulation
        else "- 当前阶段没有未完成的仿真任务。"
    )
    eval_line = (
        f"- 质量门槛：{quality['status']}；"
        + (
            "、".join(quality.get("failures", []))
            if quality and quality.get("failures")
            else "通过"
        )
        if quality
        else "- 本次未运行评测。"
    )
    metric_line = (
        f"- {eval_result['suite']}/{eval_result['split']}，{eval_result['baseline']}："
        f"page hit@3={eval_result['page_hit@3']:.1%}，MRR@10={eval_result['mrr@10']:.3f}，"
        f"p95={eval_result['latency_p95_ms']} ms"
        if eval_result
        else f"- 评测不可用：{eval_error}"
        if eval_error
        else "- 本次未运行评测。"
    )
    markdown = "\n".join(
        [
            f"# 下周计划 {next_monday.isoformat()}",
            "",
            f"阶段：{stage.get('name', stage.get('id', '未命名'))}",
            "",
            "## 论文",
            "",
            *paper_lines,
            "",
            "## 仿真",
            "",
            simulation_line,
            "",
            "## 建议复习点",
            "",
            *review_lines,
            "",
            "## 检索回归",
            "",
            eval_line,
            metric_line,
            "",
        ]
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    dashboard = _write_dashboard(paths, payload)
    payload["plan"] = str(markdown_path.relative_to(root))
    payload["dashboard"] = dashboard

    reading_rows = sync_reading(root)
    selected_paths = {item["rel_path"] for item in papers}
    for row in reading_rows:
        if row["rel_path"] in selected_paths:
            row["last_planned"] = next_monday.isoformat()
    if reading_rows:
        _write_csv(paths.reading_csv, READING_FIELDS, reading_rows)
    return payload
