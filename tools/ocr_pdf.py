# -*- coding: utf-8 -*-
"""扫描版 PDF 的 OCR：poppler 渲染 + tesseract.js，结果缓存到 kb/ocr/<slug>.jsonl"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    KB,
    RENDER_TMP,
    WS,
    ensure_tessdata,
    eprint,
    load_config,
    render_pages,
    run_ocr_worker,
    slugify,
)


def ocr_cache_path(rel_path: str) -> Path:
    return KB / "ocr" / f"{slugify(rel_path)}.jsonl"


def load_cache(rel_path: str) -> dict[int, dict]:
    path = ocr_cache_path(rel_path)
    out: dict[int, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[int(item["page"])] = item
    return out


def append_cache(rel_path: str, items: list[dict]) -> None:
    path = ocr_cache_path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def ocr_pages(rel_path: str, pages: list[int], dpi: int, workers: int, batch: int) -> dict[int, str]:
    """OCR 指定页码（1-based），返回 {页码: 文本}。已缓存的页面直接复用。"""
    cache = load_cache(rel_path)
    todo = sorted(p for p in pages if p not in cache)
    lang = ensure_tessdata()
    pdf = WS / rel_path
    slug = slugify(rel_path)
    total_rounds = (len(todo) + batch - 1) // batch if todo else 0
    for round_idx, start in enumerate(range(0, len(todo), batch), 1):
        group = todo[start : start + batch]
        workdir = RENDER_TMP / slug / f"batch{round_idx:04d}_{group[0]:04d}"
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        rendered = render_pages(pdf, group[0], group[-1], dpi, workdir)
        picked = {p: rendered[p] for p in group if p in rendered}
        results = run_ocr_worker(list(picked.values()), lang, workdir, workers)
        items = []
        for page, png in picked.items():
            item = results.get(png.name, {})
            items.append(
                {
                    "page": page,
                    "text": item.get("text", ""),
                    "confidence": item.get("confidence", 0),
                    "dpi": dpi,
                }
            )
        append_cache(rel_path, items)
        for item in items:
            cache[int(item["page"])] = item
        shutil.rmtree(workdir, ignore_errors=True)
        eprint(
            f"[ocr] {rel_path} 批次 {round_idx}/{total_rounds} 页 {group[0]}-{group[-1]} "
            f"用时 {time.time() - t0:.1f}s"
        )
    return {p: cache[p].get("text", "") for p in pages if p in cache}


def main() -> None:
    cfg = load_config()
    ocr_cfg = cfg.get("ocr", {})
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", help="相对路径，如 <课程目录>/<讲义文件>.pdf")
    ap.add_argument("--pages", help="页码，如 5-6 或 5,6,7")
    ap.add_argument("--pilot", action="store_true", help="对第一个纯图片文档做 2 页样张")
    ap.add_argument("--dpi", type=int, default=int(ocr_cfg.get("dpi", 220)))
    ap.add_argument("--workers", type=int, default=int(ocr_cfg.get("workers", 3)))
    ap.add_argument("--batch", type=int, default=int(ocr_cfg.get("batch", 24)))
    args = ap.parse_args()

    if args.pilot:
        if not args.doc:
            raise SystemExit("--pilot 也需要指定 --doc（要试 OCR 的那份扫描件）")
        rel = args.doc
        pages = _parse_pages(args.pages) or [5, 6]
    else:
        if not args.doc:
            raise SystemExit("需要 --doc 或 --pilot")
        pages = _parse_pages(args.pages)
        if not pages:
            raise SystemExit("需要 --pages")
        rel = args.doc

    texts = ocr_pages(rel, pages, args.dpi, args.workers, args.batch)
    print(f"# OCR 样张：{rel}")
    for page in pages:
        text = texts.get(page, "")
        print(f"\n===== 第 {page} 页（{len(text)} 字符）=====")
        print(text[:1500])


def _parse_pages(spec: str | None) -> list[int]:
    if not spec:
        return []
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    return pages


if __name__ == "__main__":
    main()
