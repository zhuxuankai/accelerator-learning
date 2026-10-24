from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CockpitError(RuntimeError):
    """User-facing error with an actionable message."""


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "include_dirs": ["课程一", "课程二", "文献"],
    "exclude": ["kb", "tools", "学习路线", "extensions", "examples", "tests"],
    "index": {
        "chunk_size": 700,
        "chunk_overlap": 70,
        "embedding_model": "intfloat/multilingual-e5-small",
        "rrf_k": 60,
        "candidate_k": 50,
        "max_chunks_per_doc": 3,
    },
    "ocr": {
        "enabled": True,
        "dpi": 220,
        "language": "chi_sim+eng",
        "model_version": "rapidocr-v1",
        "min_confidence": 0.60,
        "min_chars": 40,
        "max_replacement_ratio": 0.05,
        "max_noise_ratio": 0.32,
    },
    "reading": {
        "stage": "foundation",
        "slots": [
            {"category": "review", "mode": "精读"},
            {"category": "group", "mode": "泛读"},
        ],
    },
    "weekly": {
        "eval_required": True,
        "eval_suite": "local",
        "eval_split": "dev",
        "max_review_candidates": 1,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def workspace_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.environ.get("ACCKB_WORKSPACE"):
        return Path(os.environ["ACCKB_WORKSPACE"]).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def load_config(root: Path | None = None) -> tuple[dict[str, Any], Path, bool]:
    root = workspace_root(root)
    candidate = root / "kb" / "config.json"
    using_example = not candidate.exists()
    if using_example:
        candidate = root / "kb" / "config.example.json"
        if not candidate.exists():
            raise CockpitError(
                "缺少 kb/config.json，且找不到 kb/config.example.json。"
                "请从仓库模板初始化配置后重试。"
            )
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CockpitError(f"无法读取配置 {candidate}: {exc}") from exc
    cfg = _deep_merge(DEFAULT_CONFIG, raw)
    dirs = cfg.get("include_dirs")
    if not isinstance(dirs, list) or not dirs or not all(isinstance(x, str) and x for x in dirs):
        raise CockpitError("include_dirs 必须是非空字符串数组。")
    return cfg, candidate, using_example


@dataclass(frozen=True)
class Paths:
    root: Path
    state_dir: Path
    state_file: Path
    catalog_file: Path
    chroma_dir: Path
    ocr_db: Path
    eval_dir: Path
    roadmap_dir: Path
    progress_csv: Path
    reading_csv: Path
    legacy_dir: Path

    @classmethod
    def for_root(cls, root: Path) -> Paths:
        return paths(root)


def paths(root: Path | None = None) -> Paths:
    root = workspace_root(root)
    state_dir = root / "kb" / "v2"
    roadmap_dir = root / "学习路线"
    local_base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache")
    workspace_id = hashlib.sha1(str(root).casefold().encode("utf-8")).hexdigest()[:12]
    chroma_dir = local_base / "accelerator-learning-cockpit" / workspace_id / "chroma"
    return Paths(
        root=root,
        state_dir=state_dir,
        state_file=state_dir / "state.json",
        catalog_file=state_dir / "catalog.json",
        chroma_dir=chroma_dir,
        ocr_db=state_dir / "ocr.sqlite",
        eval_dir=root / "kb" / "eval" / "v2",
        roadmap_dir=roadmap_dir,
        progress_csv=roadmap_dir / "progress.csv",
        reading_csv=roadmap_dir / "reading.csv",
        legacy_dir=root / "kb" / "legacy",
    )
