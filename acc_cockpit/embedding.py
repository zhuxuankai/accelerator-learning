from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .config import CockpitError

_MODEL_CACHE: dict[tuple[str, bool], Any] = {}


def model_download_allowed(cfg: dict[str, Any]) -> bool:
    return (
        os.environ.get("ACCKB_ALLOW_MODEL_DOWNLOAD") == "1"
        or bool(cfg.get("model", {}).get("allow_download", False))
    )


def model_cache_dir() -> Path | None:
    try:
        from llama_index.core.utils import get_cache_dir
    except ImportError:
        return None
    return Path(get_cache_dir())


def model_cache_exists(model_name: str) -> bool:
    cache = model_cache_dir()
    if cache is None:
        return False
    model_root = cache / f"models--{model_name.replace('/', '--')}"
    snapshots = model_root / "snapshots"
    return snapshots.is_dir() and any(path.is_dir() for path in snapshots.iterdir())


def build_embedding_model(
    cfg: dict[str, Any],
    mock: bool = False,
    *,
    allow_download: bool | None = None,
):
    try:
        from llama_index.core.embeddings import BaseEmbedding
    except ImportError as exc:
        raise CockpitError("缺少 LlamaIndex。请执行 `pip install -e .`。") from exc

    if mock:
        cached = _MODEL_CACHE.get(("mock", True))
        if cached is not None:
            return cached

        class HashEmbedding(BaseEmbedding):
            @classmethod
            def class_name(cls) -> str:
                return "HashEmbedding"

            def _embed(self, text: str) -> list[float]:
                values = [0.0] * 64
                for token in text.lower().split():
                    digest = hashlib.sha256(token.encode()).digest()
                    values[digest[0] % 64] += 1.0 if digest[1] & 1 else -1.0
                norm = sum(value * value for value in values) ** 0.5 or 1.0
                return [value / norm for value in values]

            def _get_text_embedding(self, text: str) -> list[float]:
                return self._embed(text)

            async def _aget_text_embedding(self, text: str) -> list[float]:
                return self._embed(text)

            def _get_query_embedding(self, query: str) -> list[float]:
                return self._embed(query)

            async def _aget_query_embedding(self, query: str) -> list[float]:
                return self._embed(query)

        model = HashEmbedding()
        _MODEL_CACHE[("mock", True)] = model
        return model

    model_name = str(cfg.get("index", {}).get("embedding_model", "intfloat/multilingual-e5-small"))
    cached = _MODEL_CACHE.get((model_name, False))
    if cached is not None:
        return cached
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    except ImportError as exc:
        raise CockpitError(
            "缺少 HuggingFace embedding 组件。请执行 `pip install -e .`，"
            "首次运行会下载配置中的 multilingual-e5-small 模型。"
        ) from exc
    has_cache = model_cache_exists(model_name)
    if allow_download is None:
        allow_download = model_download_allowed(cfg)
    if not has_cache and not allow_download:
        raise CockpitError(
            f"embedding 模型 {model_name} 尚未缓存。首次下载请设置 "
            "`ACCKB_ALLOW_MODEL_DOWNLOAD=1`，或在 kb/config.json 中设置 "
            "`model.allow_download=true`。"
        )
    model = HuggingFaceEmbedding(
        model_name=model_name,
        local_files_only=not allow_download or has_cache,
    )
    _MODEL_CACHE[(model_name, False)] = model
    return model
