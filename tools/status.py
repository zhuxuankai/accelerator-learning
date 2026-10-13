# -*- coding: utf-8 -*-
"""打印知识库与学习路线的一行式状态。"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KB, ROADMAP, WS, connect_db, now_iso  # noqa: E402


def main() -> None:
    conn = connect_db(readonly=True)
    try:
        docs = conn.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
        chunks = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        ocr = conn.execute("SELECT COUNT(*) c FROM chunks WHERE ocr = 1").fetchone()["c"]
        rows = conn.execute(
            "SELECT course, COUNT(*) c FROM docs WHERE is_latest = 1 GROUP BY course ORDER BY course"
        ).fetchall()
    finally:
        conn.close()

    papers = len(list((WS / "文献").glob("*.pdf"))) if (WS / "文献").exists() else 0
    progress_path = ROADMAP / "进度追踪.csv"
    done = total = 0
    if progress_path.exists():
        with progress_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                total += 1
                if (row.get("状态") or "").strip() == "已完成":
                    done += 1

    print(f"时间：{now_iso()}")
    print(f"索引：文档 {docs} 份，块 {chunks} 个（其中 OCR 来源 {ocr} 个）")
    for row in rows:
        print(f"  - {row['course']}：{row['c']} 份（最新版）")
    print(f"文献目录 PDF：{papers} 篇")
    print(f"进度：{done}/{total} 项已完成")


if __name__ == "__main__":
    main()
