# -*- coding: utf-8 -*-
"""论文中文译本的工作流工具

  列表：  run.ps1 translate -List
  准备：  run.ps1 translate -Prepare "文献/xxx.pdf"     # 抽出带页码标记的工作文件
  状态：  run.ps1 translate -Status

译本由智能体（或人）写在 文献/译文/<同名>.zh.md，本脚本负责抽文本、判语言、查进度，
不负责机器翻译——物理公式与术语需要判断力，交给模型逐节处理更可靠。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KB, WS, load_config, now_iso  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")
QUEUE_MD = KB / "papers" / "待翻译.md"


def out_dir(cfg: dict) -> Path:
    return WS / cfg.get("translate", {}).get("out_dir", "文献/译文")


def paper_files() -> list[Path]:
    lit = WS / "文献"
    return sorted(p for p in lit.rglob("*.pdf") if "译文" not in p.parts)


def extract_pages(pdf: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def is_english(pages: list[str]) -> bool:
    text = "".join(pages)
    if not text.strip():
        return False
    return len(CJK.findall(text)) / max(1, len(text)) < 0.02


def translation_path(cfg: dict, pdf: Path) -> Path:
    return out_dir(cfg) / f"{pdf.stem}.zh.md"


def progress(md: Path) -> str:
    if not md.exists():
        return "未开始"
    text = md.read_text(encoding="utf-8")
    if re.search(r"译本状态:\s*完成", text):
        return "已完成"
    m = re.search(r"<!--\s*已译页:\s*([\d\-,\s]+)/\s*(\d+)\s*-->", text)
    if m:
        return f"进行中 {m.group(1).strip()}/{m.group(2)} 页"
    return "已完成"


def write_queue(cfg: dict) -> list[tuple[Path, str]]:
    rows = []
    for pdf in paper_files():
        pages = extract_pages(pdf)
        if not is_english(pages):
            continue
        rows.append((pdf, progress(translation_path(cfg, pdf))))

    done = [r for r in rows if r[1] == "已完成"]
    todo = [r for r in rows if r[1] != "已完成"]
    lines = [
        "# 待翻译论文清单",
        "",
        f"更新时间：{now_iso()}　英文论文 {len(rows)} 篇：已完成 {len(done)}，待处理 {len(todo)}",
        "",
        "> 译本放在 `文献/译文/<与 PDF 同名>.zh.md`；用 `run.ps1 translate -Prepare \"<pdf>\"` 抽工作文件。",
        "",
    ]
    if todo:
        lines += ["## 待处理", "", "| 论文 | 进度 |", "|---|---|"]
        for pdf, state in todo:
            lines.append(f"| {pdf.relative_to(WS).as_posix()} | {state} |")
        lines.append("")
    if done:
        lines += ["## 已完成", ""]
        lines += [f"- {pdf.relative_to(WS).as_posix()}" for pdf, _ in done]
        lines.append("")
    QUEUE_MD.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_MD.write_text("\n".join(lines), encoding="utf-8")
    return rows


def prepare(cfg: dict, rel: str) -> Path:
    pdf = WS / rel
    if not pdf.exists():
        raise SystemExit(f"找不到文件：{pdf}")
    pages = extract_pages(pdf)
    # 工作文件是中间产物，放 kb/work（不属于语料目录，不会被索引）
    target = KB / "work" / f"{pdf.stem}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 工作文件（供翻译用）：{pdf.name}",
        f"# 页数：{len(pages)}　英文论文：{is_english(pages)}",
        f"# 译本应写到：{translation_path(cfg, pdf).relative_to(WS).as_posix()}",
        f"# 抽取时间：{now_iso()}",
        "",
    ]
    for i, text in enumerate(pages, 1):
        lines.append(f"【第 {i} 页】")
        lines.append(re.sub(r"\n{3,}", "\n\n", text.strip()))
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出待翻译的英文论文")
    ap.add_argument("--status", action="store_true", help="显示每篇的译本进度")
    ap.add_argument("--prepare", help="抽出指定 PDF 的工作文件（带页码标记）")
    args = ap.parse_args()

    if args.prepare:
        target = prepare(cfg, args.prepare)
        print(f"工作文件已生成：{target.relative_to(WS)}")
        return

    rows = write_queue(cfg)
    print(f"英文论文 {len(rows)} 篇：")
    for pdf, state in rows:
        mark = "✓" if state == "已完成" else ("…" if state.startswith("进行中") else "×")
        print(f"  [{mark}] {state:16s} {pdf.relative_to(WS).as_posix()}")
    print(f"\n清单：{QUEUE_MD.relative_to(WS)}")


if __name__ == "__main__":
    main()
