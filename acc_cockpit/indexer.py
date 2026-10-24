from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import CockpitError, Paths, load_config
from .embedding import build_embedding_model
from .extract import discover_files, dump_json, extract_file, sha1_file, units_from_json
from .versions import analyze_versions, node_document_id


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CockpitError(f"无法读取 {path}: {exc}") from exc


def _archive_legacy(paths: Paths) -> str | None:
    legacy = paths.root / "kb" / "kb.sqlite"
    if not legacy.exists():
        return None
    paths.legacy_dir.mkdir(parents=True, exist_ok=True)
    target = paths.legacy_dir / "kb-v1.sqlite"
    if not target.exists():
        shutil.copy2(legacy, target)
        return str(target.relative_to(paths.root))
    return None


def _file_record(
    path: Path,
    root: Path,
    cfg: dict[str, Any],
    old: dict[str, Any] | None,
) -> tuple[dict, bool]:
    rel_path = path.relative_to(root).as_posix()
    digest = sha1_file(path)
    if old and old.get("sha1") == digest and isinstance(old.get("units"), list):
        return old, False
    try:
        units = extract_file(path, digest, cfg, paths=Paths.for_root(root))
    except Exception as exc:
        raise CockpitError(f"解析失败 {rel_path}：{exc}") from exc
    return {
        "rel_path": rel_path,
        "sha1": digest,
        "mtime": path.stat().st_mtime,
        "size": path.stat().st_size,
        "units": [unit.to_dict() for unit in units],
    }, True


def _make_nodes(
    files: dict[str, dict],
    decisions: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[list[Any], list[dict]]:
    try:
        from llama_index.core import Document
        from llama_index.core.node_parser import SentenceSplitter
    except ImportError as exc:
        raise CockpitError("缺少 LlamaIndex。请执行 `pip install -e .`。") from exc

    index_cfg = cfg.get("index", {})
    splitter = SentenceSplitter(
        chunk_size=int(index_cfg.get("chunk_size", 700)),
        chunk_overlap=int(index_cfg.get("chunk_overlap", 70)),
    )
    nodes = []
    flat: list[dict] = []
    for rel_path, record in sorted(files.items()):
        decision = decisions[rel_path]
        course = Path(rel_path).parts[0]
        suffix = Path(rel_path).suffix.lower()
        kind = "paper" if course == "文献" else ("slide" if suffix in {".pdf", ".pptx"} else "doc")
        for raw in units_from_json(record["units"]):
            if not raw.text.strip():
                continue
            metadata = {
                "rel_path": rel_path,
                "course": course,
                "kind": kind,
                "unit": raw.unit,
                "unit_label": raw.unit_label,
                "ocr": raw.ocr,
                "ocr_confidence": raw.ocr_confidence,
                "ocr_quality": raw.ocr_quality,
                "warning": raw.warning or "",
                "file_sha1": record["sha1"],
                "version_group": decision.version_group,
                "version_basis": decision.version_basis,
                "authoritative": int(decision.authoritative),
                "search_eligible": int(decision.search_eligible),
                "ambiguous": int(decision.ambiguous),
                "semantic_eligible": int(raw.semantic_eligible),
            }
            document = Document(text=raw.text, metadata=metadata, doc_id=f"{record['sha1']}:{raw.unit}")
            parsed = splitter.get_nodes_from_documents([document])
            for part, node in enumerate(parsed):
                node.id_ = node_document_id(rel_path, record["sha1"], raw.unit, part)
                item = {
                    "id": node.id_,
                    "text": node.get_content(),
                    **metadata,
                }
                flat.append(item)
                nodes.append(node)
    return nodes, flat


def _build_chroma(nodes: list[Any], paths: Paths, cfg: dict[str, Any], mock_embedding: bool) -> int:
    semantic_nodes = [
        node
        for node in nodes
        if int(node.metadata.get("semantic_eligible") or 0)
    ]
    try:
        import chromadb
    except ImportError as exc:
        raise CockpitError("缺少 Chroma/LlamaIndex 依赖。请执行 `pip install -e .`。") from exc

    if paths.chroma_dir.exists():
        shutil.rmtree(paths.chroma_dir)
    paths.chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(paths.chroma_dir))
    collection_name = "acc-cockpit-v2"
    collection = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
    embed_model = build_embedding_model(cfg, mock=mock_embedding)
    if semantic_nodes:
        for start in range(0, len(semantic_nodes), 64):
            batch = semantic_nodes[start : start + 64]
            texts = [node.get_content() for node in batch]
            if hasattr(embed_model, "get_text_embedding_batch"):
                embeddings = embed_model.get_text_embedding_batch(texts, show_progress=False)
            else:
                embeddings = [embed_model.get_text_embedding(text) for text in texts]
            collection.add(
                ids=[node.id_ for node in batch],
                embeddings=embeddings,
                metadatas=[
                    {
                        "search_eligible": int(node.metadata.get("search_eligible") or 0),
                        "course": str(node.metadata.get("course") or ""),
                        "kind": str(node.metadata.get("kind") or ""),
                    }
                    for node in batch
                ],
            )
    collection.count()
    return len(semantic_nodes)


def build_index(
    root: Path,
    *,
    full: bool = False,
    only: str | None = None,
    mock_embedding: bool = False,
) -> dict[str, Any]:
    cfg, config_file, using_example = load_config(root)
    embedding_model = str(cfg.get("index", {}).get("embedding_model", "intfloat/multilingual-e5-small"))
    root = Path(root).resolve()
    paths = Paths.for_root(root)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    legacy_archive = _archive_legacy(paths)

    previous = _read_json(paths.state_file, {"version": 2, "files": {}})
    old_files = previous.get("files", {}) if not full else {}
    discovered = discover_files(root, cfg)
    selected = []
    requested = {part.strip().replace("\\", "/") for part in only.split(",")} if only else None
    for path in discovered:
        rel_path = path.relative_to(root).as_posix()
        if requested is None or rel_path in requested:
            selected.append(path)
    if requested:
        missing = requested - {path.relative_to(root).as_posix() for path in selected}
        if missing:
            raise CockpitError(f"-Only 路径不在语料范围内：{', '.join(sorted(missing))}")

    files: dict[str, dict] = {}
    changed: list[str] = []
    removed: list[str] = []
    selected_rels = {path.relative_to(root).as_posix() for path in selected}
    for rel_path, record in old_files.items():
        if requested is None and rel_path not in selected_rels:
            if rel_path not in {rel for rel in old_files if (root / rel).exists()}:
                removed.append(rel_path)
            continue
        if rel_path not in selected_rels:
            files[rel_path] = record
    for path in selected:
        rel_path = path.relative_to(root).as_posix()
        record, was_changed = _file_record(path, root, cfg, old_files.get(rel_path))
        files[rel_path] = record
        if was_changed:
            changed.append(rel_path)

    if (
        not full
        and not changed
        and not removed
        and paths.state_file.exists()
        and paths.catalog_file.exists()
        and paths.chroma_dir.exists()
        and previous.get("embedding_model") == embedding_model
    ):
        return {
            "status": "no_changes",
            "indexed_files": len(files),
            "changed_files": [],
            "removed_files": [],
            "nodes": previous.get("node_count", 0),
            "semantic_nodes": previous.get("semantic_node_count", 0),
            "warnings": previous.get("warnings", []),
            "legacy_archive": legacy_archive,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }

    decisions = analyze_versions(
        {"rel_path": rel, "sha1": rec["sha1"], "mtime": rec.get("mtime", 0)}
        for rel, rec in files.items()
    )
    nodes, flat = _make_nodes(files, decisions, cfg)
    semantic_count = _build_chroma(nodes, paths, cfg, mock_embedding)
    warnings = sorted(
        {
            decision.warning
            for decision in decisions.values()
            if decision.warning and ("歧义" in decision.warning or "多个文件" in decision.warning)
        }
    )
    state = {
        "version": 2,
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "config_file": config_file.relative_to(root).as_posix(),
        "using_example_config": using_example,
        "embedding_model": embedding_model,
        "files": files,
        "changed": changed,
        "removed": removed,
        "node_count": len(flat),
        "semantic_node_count": semantic_count,
        "warnings": warnings,
    }
    dump_json(paths.catalog_file, {"nodes": flat})
    dump_json(paths.state_file, state)
    return {
        "status": "ok",
        "indexed_files": len(files),
        "changed_files": changed,
        "removed_files": removed,
        "nodes": len(flat),
        "semantic_nodes": semantic_count,
        "warnings": warnings,
        "legacy_archive": legacy_archive,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
