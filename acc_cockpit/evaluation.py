from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from .config import CockpitError, Paths
from .retrieval import RetrieverMode, query


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise CockpitError(f"评测集不存在：{path}")
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CockpitError(f"{path}:{number} 不是有效 JSON：{exc}") from exc
        if row.get("approved") is not True:
            raise CockpitError(
                f"{path}:{number} 尚未由用户审核（approved != true），不能作为发布质量证明。"
            )
        rows.append(row)
    return rows
def _relevant_pairs(question: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(item["rel_path"]), str(item["unit_label"]))
        for item in question.get("relevant", [])
    }


def evaluate(
    root: Path,
    *,
    suite: str = "demo",
    baseline: RetrieverMode = "hybrid",
    mock_embedding: bool = False,
    split: str = "dev",
) -> dict[str, Any]:
    paths = Paths.for_root(Path(root).resolve())
    path = paths.eval_dir / f"{suite}-{split}.jsonl"
    if suite == "local" and not path.exists():
        raise CockpitError(
            f"缺少经用户审核的本地评测集：{path}。"
            f"请复制 {paths.eval_dir / f'local-{split}.template.jsonl'} 后填写精确页码与证据，"
            "并把 approved 改为 true。"
        )
    questions = _load_jsonl(path)
    latencies: list[float] = []
    page_hit_3 = 0
    recall_50 = 0
    reciprocal_rank = 0.0
    ndcg_10 = 0.0
    empty = 0
    details = []

    for question in questions:
        started = time.perf_counter()
        response = query(
            root,
            question["query"],
            top_k=50,
            mode=baseline,
            mock_embedding=mock_embedding,
        )
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        relevant = _relevant_pairs(question)
        results = response["results"]
        found = [(str(item["rel_path"]), str(item["unit_label"])) for item in results]
        hit3 = any(pair in relevant for pair in found[:3])
        recall = any(pair in relevant for pair in found[:50])
        first_rank = next((rank for rank, pair in enumerate(found[:10], 1) if pair in relevant), None)
        page_hit_3 += int(hit3)
        recall_50 += int(recall)
        empty += int(not found)
        if first_rank:
            reciprocal_rank += 1.0 / first_rank
            ndcg_10 += 1.0 / math.log2(first_rank + 1)
        details.append(
            {
                "id": question["id"],
                "hit@3": hit3,
                "recall@50": recall,
                "first_relevant_rank": first_rank,
                "elapsed_ms": round(elapsed, 2),
            }
        )
    count = max(1, len(questions))
    latencies.sort()
    return {
        "status": "ok",
        "suite": suite,
        "split": split,
        "baseline": baseline,
        "questions": len(questions),
        "page_hit@3": round(page_hit_3 / count, 4),
        "recall@50": round(recall_50 / count, 4),
        "mrr@10": round(reciprocal_rank / count, 4),
        "ndcg@10": round(ndcg_10 / count, 4),
        "empty_rate": round(empty / count, 4),
        "latency_p50_ms": round(latencies[len(latencies) // 2], 2) if latencies else 0,
        "latency_p95_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 2)
        if latencies
        else 0,
        "details": details,
    }


def quality_gate(result: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    page_min = float(thresholds.get("page_hit_at_3", 0.8))
    recall_min = float(thresholds.get("recall_at_50", 0.9))
    empty_max = float(thresholds.get("empty_rate_max", 0.1))
    failures = []
    if float(result["page_hit@3"]) < page_min:
        failures.append(f"page_hit@3 {result['page_hit@3']:.3f} < {page_min:.3f}")
    if float(result["recall@50"]) < recall_min:
        failures.append(f"recall@50 {result['recall@50']:.3f} < {recall_min:.3f}")
    if float(result["empty_rate"]) > empty_max:
        failures.append(f"empty_rate {result['empty_rate']:.3f} > {empty_max:.3f}")
    return {
        "status": "failed" if failures else "passed",
        "thresholds": {
            "page_hit_at_3": page_min,
            "recall_at_50": recall_min,
            "empty_rate_max": empty_max,
        },
        "metrics": {
            "page_hit@3": result["page_hit@3"],
            "recall@50": result["recall@50"],
            "empty_rate": result["empty_rate"],
        },
        "failures": failures,
    }
