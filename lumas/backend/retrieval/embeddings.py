"""EmbeddingProvider — abstract interface for generating embeddings.

Desktop: uses sentence-transformers (all-MiniLM-L6-v2).
Android: keyword/substring fallback (no on-device embedder this week).

The RetrievalService doesn't know which strategy is behind this interface.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...


class MiniLMEmbedding(EmbeddingProvider):
    """Desktop embedding provider using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._dimension = 384  # all-MiniLM-L6-v2

    def _lazy_load(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        except ImportError:
            logger.error(
                "sentence-transformers not installed. Install with: pip install sentence-transformers"
            )
            raise

    def embed(self, text: str) -> list[float]:
        self._lazy_load()
        return self._model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._lazy_load()
        return self._model.encode(texts).tolist()

    @property
    def dimension(self) -> int:
        return self._dimension


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
