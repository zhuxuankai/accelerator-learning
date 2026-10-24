from __future__ import annotations

import json
import re
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from .config import CockpitError, Paths, load_config
from .embedding import build_embedding_model

RetrieverMode = Literal["lexical", "vector", "hybrid"]
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def chinese_bigram_tokens(text: str) -> list[str]:
    tokens = [match.group(0).lower() for match in LATIN_RUN.finditer(text)]
    for match in CJK_RUN.finditer(text):
        value = match.group(0)
        if len(value) == 1:
            tokens.append(value)
        else:
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
    return tokens


def _load_state(paths: Paths) -> dict[str, Any]:
    if not paths.state_file.exists() or not paths.catalog_file.exists():
        raise CockpitError("v2 索引不存在。请先运行 `run.ps1 index`。")
    try:
        return json.loads(paths.state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CockpitError(f"索引状态损坏：{paths.state_file}: {exc}") from exc


def _load_nodes(paths: Paths):
    try:
        from llama_index.core.schema import TextNode
    except ImportError as exc:
        raise CockpitError("缺少 LlamaIndex。请执行 `pip install -e .`。") from exc
    raw = json.loads(paths.catalog_file.read_text(encoding="utf-8"))
    nodes = []
    for item in raw.get("nodes", []):
        metadata = {key: value for key, value in item.items() if key not in {"id", "text"}}
        nodes.append(TextNode(id_=item["id"], text=item["text"], metadata=metadata))
    return nodes


def _metadata_matches(node: Any, course: str | None, kind: str | None, all_versions: bool) -> bool:
    metadata = node.metadata
    if course and metadata.get("course") != course:
        return False
    if kind and metadata.get("kind") != kind:
        return False
    if not all_versions and not metadata.get("search_eligible", False):
        return False
    return True


def _vector_retriever(
    paths: Paths,
    cfg: dict[str, Any],
    mock_embedding: bool,
    course: str | None,
    kind: str | None,
    all_versions: bool,
):
    try:
        import chromadb
        from llama_index.core.retrievers import BaseRetriever
        from llama_index.core.schema import NodeWithScore
    except ImportError as exc:
        raise CockpitError("缺少 Chroma/LlamaIndex 依赖。请执行 `pip install -e .`。") from exc

    client = chromadb.PersistentClient(path=str(paths.chroma_dir))
    collection = client.get_collection("acc-cockpit-v2")
    embed_model = build_embedding_model(cfg, mock=mock_embedding)
    where_parts = []
    if not all_versions:
        where_parts.append({"search_eligible": 1})
    if course:
        where_parts.append({"course": course})
    if kind:
        where_parts.append({"kind": kind})
    if not where_parts:
        where = None
    elif len(where_parts) == 1:
        where = where_parts[0]
    else:
        where = {"$and": where_parts}
    nodes_by_id = {node.id_: node for node in _load_nodes(paths)}

    class CatalogChromaRetriever(BaseRetriever):
        def _retrieve(self, query_bundle):
            embedding = embed_model.get_query_embedding(query_bundle.query_str)
            response = collection.query(
                query_embeddings=[embedding],
                n_results=int(cfg.get("index", {}).get("candidate_k", 50)),
                where=where,
                include=["distances"],
            )
            ids = response.get("ids", [[]])[0]
            distances = response.get("distances", [[]])[0]
            return [
                NodeWithScore(node=nodes_by_id[node_id], score=1.0 - float(distance))
                for node_id, distance in zip(ids, distances, strict=False)
                if node_id in nodes_by_id
            ]

    return CatalogChromaRetriever()


def _lexical_retriever(
    paths: Paths,
    cfg: dict[str, Any],
    course: str | None,
    kind: str | None,
    all_versions: bool,
):
    try:
        from llama_index.retrievers.bm25 import BM25Retriever
    except ImportError as exc:
        raise CockpitError("缺少 LlamaIndex BM25 组件。请执行 `pip install -e .`。") from exc
    nodes = [node for node in _load_nodes(paths) if _metadata_matches(node, course, kind, all_versions)]
    if not nodes:
        return None
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The tokenizer parameter is deprecated.*")
        return BM25Retriever.from_defaults(
            nodes=nodes,
            similarity_top_k=min(int(cfg.get("index", {}).get("candidate_k", 50)), len(nodes)),
            language="zh",
            skip_stemming=True,
            tokenizer=chinese_bigram_tokens,
        )


def _normalise_result(item: Any) -> dict[str, Any]:
    node = item.node
    metadata = node.metadata
    return {
        "id": node.id_,
        "text": node.get_content(),
        "rel_path": metadata.get("rel_path"),
        "unit_label": metadata.get("unit_label"),
        "course": metadata.get("course"),
        "kind": metadata.get("kind"),
        "ocr": bool(metadata.get("ocr")),
        "ocr_quality": metadata.get("ocr_quality"),
        "version_group": metadata.get("version_group"),
        "version_basis": metadata.get("version_basis"),
        "ambiguous": bool(metadata.get("ambiguous")),
        "warning": metadata.get("warning") or "",
    }


def _rrf(items: list[Any], constant: int) -> dict[str, dict[str, Any]]:
    ranked: dict[str, dict[str, Any]] = {}
    for rank, item in enumerate(items, 1):
        value = _normalise_result(item)
        key = value["id"]
        entry = ranked.setdefault(key, {**value, "rrf_score": 0.0})
        entry["rrf_score"] += 1.0 / (constant + rank)
    return ranked


def query(
    root: Path,
    text: str,
    *,
    course: str | None = None,
    kind: str | None = None,
    top_k: int = 8,
    all_versions: bool = False,
    mode: RetrieverMode = "hybrid",
    mock_embedding: bool = False,
) -> dict[str, Any]:
    start = time.perf_counter()
    cfg, _, _ = load_config(root)
    paths = Paths.for_root(Path(root).resolve())
    _load_state(paths)
    vector_results: list[Any] = []
    lexical_results: list[Any] = []
    warnings: list[str] = []
    errors: list[str] = []

    if mode in {"hybrid", "vector"}:
        try:
            retriever = _vector_retriever(paths, cfg, mock_embedding, course, kind, all_versions)
            vector_results = retriever.retrieve(text)
        except Exception as exc:
            errors.append(f"向量检索失败：{exc}")

    if mode in {"hybrid", "lexical"}:
        try:
            retriever = _lexical_retriever(paths, cfg, course, kind, all_versions)
            if retriever is not None:
                lexical_results = [
                    item
                    for item in retriever.retrieve(text)
                    if (getattr(item, "score", 0.0) or 0.0) > 0.0
                ]
        except Exception as exc:
            errors.append(f"词法检索失败：{exc}")

    if mode == "hybrid":
        if not vector_results and not lexical_results:
            if errors:
                raise CockpitError("混合检索不可用：" + "；".join(errors))
            candidates = []
        elif not vector_results:
            warnings.append("词法召回有效，但向量召回为空；本次使用词法结果。")
            candidates = []
            for rank, item in enumerate(lexical_results, 1):
                value = _normalise_result(item)
                value["vector_rank"] = None
                value["lexical_rank"] = rank
                value["fused_score"] = round(float(getattr(item, "score", 0.0) or 0.0), 8)
                candidates.append(value)
        elif not lexical_results:
            warnings.append("向量召回有效，但词法召回为空；本次使用向量结果。")
            candidates = []
            for rank, item in enumerate(vector_results, 1):
                value = _normalise_result(item)
                value["vector_rank"] = rank
                value["lexical_rank"] = None
                value["fused_score"] = round(float(getattr(item, "score", 0.0) or 0.0), 8)
                candidates.append(value)
        else:
            constant = int(cfg.get("index", {}).get("rrf_k", 60))
            vector_map = _rrf(vector_results, constant)
            lexical_map = _rrf(lexical_results, constant)
            combined: dict[str, dict[str, Any]] = {}
            for key in set(vector_map) | set(lexical_map):
                left = vector_map.get(key)
                right = lexical_map.get(key)
                base = {**(right or left or {})}
                base["vector_rank"] = next(
                    (rank for rank, item in enumerate(vector_results, 1) if item.node.id_ == key),
                    None,
                )
                base["lexical_rank"] = next(
                    (rank for rank, item in enumerate(lexical_results, 1) if item.node.id_ == key),
                    None,
                )
                base["fused_score"] = round(
                    (left or {}).get("rrf_score", 0.0) + (right or {}).get("rrf_score", 0.0),
                    8,
                )
                combined[key] = base
            candidates = sorted(
                combined.values(),
                key=lambda item: (
                    item["fused_score"],
                    -min(item["vector_rank"] or 10**9, item["lexical_rank"] or 10**9),
                ),
                reverse=True,
            )
    elif mode == "vector":
        if not vector_results:
            raise CockpitError("向量索引为空或查询失败：" + "；".join(errors))
        candidates = []
        for rank, item in enumerate(vector_results, 1):
            value = _normalise_result(item)
            value["vector_rank"] = rank
            value["lexical_rank"] = None
            value["fused_score"] = round(float(getattr(item, "score", 0.0) or 0.0), 8)
            candidates.append(value)
    else:
        if not lexical_results:
            if errors:
                raise CockpitError("词法索引为空或查询失败：" + "；".join(errors))
            candidates = []
        else:
            candidates = []
            for rank, item in enumerate(lexical_results, 1):
                value = _normalise_result(item)
                value["vector_rank"] = None
                value["lexical_rank"] = rank
                value["fused_score"] = round(float(getattr(item, "score", 0.0) or 0.0), 8)
                candidates.append(value)

    per_doc: dict[str, int] = defaultdict(int)
    results = []
    for item in candidates:
        rel_path = str(item.get("rel_path") or "")
        if per_doc[rel_path] >= int(cfg.get("index", {}).get("max_chunks_per_doc", 3)):
            continue
        per_doc[rel_path] += 1
        results.append(item)
        if len(results) >= top_k:
            break
    if any(item.get("ambiguous") for item in results):
        warnings.append("结果含无法判定先后的同名版本；默认没有隐藏其它版本。")
    warnings.extend(item["warning"] for item in results if item.get("warning"))
    if any(item.get("ocr_quality") == "low" for item in results):
        warnings.append("部分命中页 OCR 质量低，仅适合定位，不适合作为公式原文依据。")
    return {
        "status": "ok" if results else "no_match",
        "query": text,
        "mode": mode,
        "results": results,
        "diagnostics": {
            "warnings": sorted(set(warnings)),
            "errors": errors,
            "vector_candidates": len(vector_results),
            "lexical_candidates": len(lexical_results),
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    }
