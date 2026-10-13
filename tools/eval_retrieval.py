# -*- coding: utf-8 -*-
"""检索回归：跑 kb/eval/questions.jsonl，统计 top-N 命中率。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KB  # noqa: E402
from query import search  # noqa: E402

QUESTIONS = KB / "eval" / "questions.jsonl"


def main() -> None:
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    rows = [
        json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    hits = 0
    misses = []
    print(f"共 {len(rows)} 题，命中判据：top-{top_n} 内出现期望文件名片段\n")
    for row in rows:
        results = search(row["question"], course=row.get("course"), k=top_n)
        expects = row["expect"]
        if isinstance(expects, str):
            expects = [expects]
        ok = any(pat in r["rel_path"] for r in results for pat in expects)
        hits += 1 if ok else 0
        mark = "OK " if ok else "MISS"
        first = results[0]["rel_path"] + " " + results[0]["unit_label"] if results else "（无结果）"
        print(f"[{mark}] {row['id']:8s} {row['question'][:34]:36s} -> {first}")
        if not ok:
            misses.append(row["id"])
    rate = hits / len(rows) if rows else 0
    print(f"\n命中率 {hits}/{len(rows)} = {rate:.0%}")
    if misses:
        print("未命中：" + "、".join(misses))


if __name__ == "__main__":
    main()
