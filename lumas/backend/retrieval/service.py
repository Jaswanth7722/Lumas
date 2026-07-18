"""RetrievalService — retrieves relevant chunks for a query.

Desktop: uses embedding similarity search via EmbeddingProvider.
Android: keyword/substring fallback (no on-device embedder this week).

The service interface stays the same regardless of the strategy behind it.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Optional

from .embeddings import EmbeddingProvider, MiniLMEmbedding, cosine_similarity
from ..config import Settings
from ..storage.database import Storage

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieves relevant document chunks for a given query."""

    def __init__(
        self,
        storage: Storage,
        embedding_provider: Optional[EmbeddingProvider] = None,
        settings: Optional[Settings] = None,
    ):
        self.storage = storage
        self.settings = settings or Settings.load()
        self.embedding_provider = embedding_provider

    def _ensure_embeddings(self):
        """Lazy-load the embedding provider if needed."""
        if self.embedding_provider is None:
            try:
                self.embedding_provider = MiniLMEmbedding(
                    model_name=self.settings.embedding_model
                )
            except Exception as e:
                logger.warning(
                    "Failed to load embedding model, falling back to keyword search: %s", e
                )
                self.embedding_provider = None

    def retrieve(
        self, query: str, top_k: int = 5, document_id: Optional[str] = None
    ) -> list[dict]:
        """Retrieve the most relevant chunks for a query.

        Uses embedding search if available, otherwise keyword fallback.
        """
        chunks = self.storage.get_all_chunks()
        if document_id:
            chunks = [c for c in chunks if c["document_id"] == document_id]

        if not chunks:
            return []

        # Only initialize the desktop embedding model when this corpus already
        # has vectors.  A fresh install (and Android) should use the cheap
        # keyword path immediately instead of downloading/loading a model just
        # to discover that there is nothing to compare against.
        has_embeddings = any(self.storage.get_embedding(chunk["id"]) for chunk in chunks)
        if has_embeddings or self.embedding_provider is not None:
            try:
                self._ensure_embeddings()
                if self.embedding_provider is not None:
                    return self._embedding_retrieve(query, chunks, top_k)
            except Exception as e:
                logger.warning("Embedding search failed, falling back to keyword: %s", e)

        # Keyword fallback
        return self._keyword_retrieve(query, chunks, top_k)

    def _embedding_retrieve(
        self, query: str, chunks: list[dict], top_k: int
    ) -> list[dict]:
        """Retrieve chunks using embedding similarity."""
        query_embedding = self.embedding_provider.embed(query)

        # Get stored embeddings for chunks
        chunk_scores = []
        for chunk in chunks:
            emb_bytes = self.storage.get_embedding(chunk["id"])
            if emb_bytes:
                import struct
                vector = list(struct.unpack(f"{len(emb_bytes) // 4}f", emb_bytes))
                score = cosine_similarity(query_embedding, vector)
                chunk_scores.append((score, chunk))

        if not chunk_scores:
            # No embeddings stored; compute on-the-fly for available chunks
            embeddings = self.embedding_provider.embed_batch(
                [c["content"] for c in chunks]
            )
            for emb, chunk in zip(embeddings, chunks):
                score = cosine_similarity(query_embedding, emb)
                chunk_scores.append((score, chunk))

        chunk_scores.sort(key=lambda x: x[0], reverse=True)
        top = chunk_scores[:top_k]

        results = []
        for score, chunk in top:
            chunk["score"] = round(score, 4)
            results.append(chunk)
        return results

    def _keyword_retrieve(
        self, query: str, chunks: list[dict], top_k: int
    ) -> list[dict]:
        """Retrieve chunks using simple keyword overlap scoring.

        Used as fallback on desktop when embeddings aren't available,
        and as the primary strategy on Android.
        """
        query_terms = set(re.findall(r'\w+', query.lower()))
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "can", "could", "shall", "should", "may", "might", "to",
            "of", "in", "for", "on", "with", "at", "by", "from", "as",
            "into", "through", "during", "before", "after", "about",
            "between", "this", "that", "these", "those", "it", "its",
        }
        query_terms = query_terms - stop_words

        if not query_terms:
            return chunks[:top_k]

        scored = []
        for chunk in chunks:
            chunk_terms = set(re.findall(r'\w+', chunk["content"].lower()))
            overlap = len(query_terms & chunk_terms)
            if overlap > 0:
                # TF-like scoring: normalize by chunk length
                score = overlap / math.log(len(chunk_terms) + 1)
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        results = []
        for score, chunk in top:
            chunk["score"] = round(score, 4)
            results.append(chunk)
        return results
