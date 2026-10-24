from __future__ import annotations

import hashlib
from typing import Any

from .config import CockpitError

_MODEL_CACHE: dict[tuple[str, bool], Any] = {}


def build_embedding_model(cfg: dict[str, Any], mock: bool = False):
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
    model = HuggingFaceEmbedding(model_name=model_name)
    _MODEL_CACHE[(model_name, False)] = model
    return model
