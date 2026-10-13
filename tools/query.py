# -*- coding: utf-8 -*-
"""检索：FTS5 召回 + 术语扩展 + 重排，输出带出处的 JSON

用法：
  run.ps1 query "<你的问题>" [-Course <课程目录>] [-K 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    STOPWORDS,
    connect_db,
    expand_terms,
    norm_text,
    raw_terms,
    token_list,
)

RERANK = {"bm25": 0.45, "coverage": 0.30, "phrase": 0.25}


def _match_string(tokens: list[str], mode: str) -> str:
    unique = []
    for t in tokens:
        if t not in unique:
            unique.append(t)
    joiner = " AND " if mode == "and" else " OR "
    return joiner.join(f'"{t}"' for t in unique)


def _recall(conn, match: str, course, kind, all_versions, limit=200):
    sql = ["SELECT c.id, c.text, c.unit_label, c.course, c.kind, c.rel_path, c.ocr,"]
    sql.append("       c.is_latest, d.title, d.version_rank, bm25(chunks_fts) AS bm")
    sql.append("FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid")
    sql.append("JOIN docs d ON d.id = c.doc_id")
    sql.append("WHERE chunks_fts MATCH ?")
    params: list = [match]
    if course:
        sql.append("AND c.course = ?")
        params.append(course)
    if kind:
        sql.append("AND c.kind = ?")
        params.append(kind)
    if not all_versions:
        sql.append("AND c.is_latest = 1")
    sql.append("ORDER BY bm LIMIT ?")
    params.append(limit)
    try:
        return conn.execute(" ".join(sql), params).fetchall()
    except Exception:
        return []


def _phrase_ratio(query_norm: str, chunk_norm: str) -> tuple[float, str]:
    """返回 (命中比例, 最长命中片段)。"""
    if not query_norm or not chunk_norm:
        return 0.0, ""
    max_len = min(len(query_norm), 24)
    for size in range(max_len, 1, -1):
        for start in range(0, len(query_norm) - size + 1):
            sub = query_norm[start : start + size]
            if sub and sub in chunk_norm:
                return size / len(query_norm), sub
    return 0.0, ""


def _coverage(query_terms: set[str], chunk_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    hit = sum(1 for t in query_terms if t in chunk_terms)
    return hit / len(query_terms)


def _snippet(text: str, phrase: str, width: int = 700) -> str:
    text = text.strip()
    if len(text) <= width:
        return text
    if phrase:
        idx = norm_text(text).find(phrase)
        if idx > 0:
            start = max(0, idx - width // 3)
            return ("…" if start else "") + text[start : start + width] + "…"
    return text[:width] + "…"


def search(query: str, course=None, kind=None, k=8, all_versions=False, include_full=False):
    tokens = [t for t in token_list(query) if t not in STOPWORDS]
    if not tokens:
        tokens = token_list(query)
    extra = expand_terms(query)
    recall_tokens = tokens + extra

    conn = connect_db(readonly=True)
    try:
        rows = _recall(conn, _match_string(tokens, "and"), course, kind, all_versions, limit=120)
        if len(rows) < 3:
            rows = _recall(conn, _match_string(recall_tokens, "or"), course, kind, all_versions, limit=200)
        if not rows:
            rows = _recall(conn, _match_string(tokens, "or"), course, kind, all_versions, limit=200)
        if not rows:
            return []

        query_norm = norm_text(query)
        q_terms = set(raw_terms(query)) | set(tokens)
        best_bm = min(r["bm"] for r in rows) or -1.0
        scored = []
        for row in rows:
            text = row["text"] or ""
            text_norm = norm_text(text)
            cov = _coverage(q_terms, set(raw_terms(text)) | set(token_list(text)))
            phrase, matched = _phrase_ratio(query_norm, text_norm)
            bm_norm = (row["bm"] / best_bm) if best_bm else 0.0
            score = (
                RERANK["bm25"] * bm_norm
                + RERANK["coverage"] * cov
                + RERANK["phrase"] * phrase
            )
            if course and row["course"] == course:
                score += 0.10
            if not row["is_latest"]:
                score *= 0.5
            if row["ocr"]:
                score *= 0.92
            item = {
                "score": round(score, 4),
                "rel_path": row["rel_path"],
                "title": row["title"],
                "course": row["course"],
                "kind": row["kind"],
                "unit_label": row["unit_label"],
                "version_rank": row["version_rank"],
                "ocr": bool(row["ocr"]),
                "coverage": round(cov, 3),
                "phrase_hit": matched,
                "text": text if include_full else _snippet(text, matched),
            }
            scored.append(item)
        scored.sort(key=lambda x: x["score"], reverse=True)

        # 同一文档最多保留 3 条，避免一份讲义刷屏
        per_doc: dict[str, int] = {}
        picked = []
        for item in scored:
            used = per_doc.get(item["rel_path"], 0)
            if used >= 3:
                continue
            per_doc[item["rel_path"]] = used + 1
            picked.append(item)
            if len(picked) >= k:
                break
        return picked
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--course")
    ap.add_argument("--kind", choices=["slide", "book", "paper", "doc"])
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--all-versions", action="store_true")
    ap.add_argument("--full-text", action="store_true")
    ap.add_argument("--json", action="store_true", help="输出 JSON（默认也是 JSON，保留兼容）")
    args = ap.parse_args()
    results = search(
        args.query, args.course, args.kind, args.k, args.all_versions, args.full_text
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
