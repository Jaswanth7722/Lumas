"""Hybrid retrieval for the desktop document-grounded tutor.

The service ranks only relevant chunks from the active document.  It combines
MiniLM semantic similarity with lexical coverage, filters weak matches, and
uses a small MMR-style diversity pass so adjacent overlapping chunks do not
consume the entire context window.
"""

from __future__ import annotations

import logging
import math
import re
import struct
from typing import Optional

from .embeddings import EmbeddingProvider, MiniLMEmbedding, cosine_similarity
from ..config import Settings
from ..storage.database import Storage

logger = logging.getLogger(__name__)
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "before", "between",
    "but", "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "how", "in", "into", "is", "it", "its", "may", "might",
    "of", "on", "or", "should", "that", "the", "their", "these", "this",
    "those", "through", "to", "was", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your", "list", "lists",
    "show", "give", "tell", "name", "names", "all",
}


class RetrievalService:
    """Retrieve a small, relevant evidence set from the active document."""

    def __init__(
        self,
        storage: Storage,
        embedding_provider: Optional[EmbeddingProvider] = None,
        settings: Optional[Settings] = None,
    ):
        self.storage = storage
        self.settings = settings or Settings.load()
        self.embedding_provider = embedding_provider
        self._embedding_failed = False

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            token for token in _TOKEN_RE.findall(text.lower())
            if (len(token) > 1 or token.isdigit()) and token not in _STOP_WORDS
        }

    def _ensure_embeddings(self) -> None:
        """Lazy-load the local embedding provider only when vectors exist."""
        if self.embedding_provider is not None or self._embedding_failed:
            return
        try:
            self.embedding_provider = MiniLMEmbedding(
                model_name=self.settings.embedding_model
            )
        except Exception as exc:
            logger.warning("Embedding model unavailable; using lexical retrieval: %s", exc)
            self.embedding_provider = None
            self._embedding_failed = True

    def retrieve(
        self, query: str, top_k: int = 5, document_id: Optional[str] = None
    ) -> list[dict]:
        """Return only the strongest, diverse chunks for ``query``.

        ``top_k`` is an upper bound, not a promise: weak or unrelated chunks
        are omitted.  When a document is selected, chunks from other PDFs are
        never considered.
        """
        top_k = max(1, min(int(top_k), 8))
        chunks = self.storage.get_all_chunks()
        if document_id:
            chunks = [chunk for chunk in chunks if chunk["document_id"] == document_id]
        if not chunks or not query.strip():
            return []

        lexical = self._lexical_scores(query, chunks)
        chunk_ids = {chunk["id"] for chunk in chunks}
        stored_embeddings = {
            chunk_id: vector
            for chunk_id, vector in self.storage.get_all_embeddings()
            if chunk_id in chunk_ids
        }
        semantic: dict[str, float] = {}
        if stored_embeddings or self.embedding_provider is not None:
            try:
                semantic = self._semantic_scores(query, chunks, stored_embeddings)
            except Exception as exc:
                logger.warning("Semantic retrieval failed; using lexical scores: %s", exc)
                self.embedding_provider = None
                self._embedding_failed = True

        ranked = []
        for chunk in chunks:
            chunk_id = chunk["id"]
            keyword_score = lexical.get(chunk_id, 0.0)
            semantic_score = max(0.0, semantic.get(chunk_id, 0.0))
            if semantic:
                # Semantic similarity handles paraphrases; lexical coverage
                # keeps exact lesson names and chapter numbers precise.
                score = 0.72 * semantic_score + 0.28 * keyword_score
            else:
                score = keyword_score
            ranked.append((score, semantic_score, keyword_score, chunk))

        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked or ranked[0][0] <= 0.0:
            return []

        # Do not pass low-confidence neighbors just because top_k is large.
        # The relative threshold adapts to short and long documents.
        top_score = ranked[0][0]
        minimum = max(0.08, top_score * 0.42)
        candidates = [item for item in ranked if item[0] >= minimum]
        if semantic and not any(value > 0.0 for value in lexical.values()):
            candidates = [item for item in candidates if item[1] >= 0.18]
        # Exact section terms (for example, "appendix" or "chapter 1") are
        # stronger than a loose semantic neighbor.  When one is present,
        # keep only chunks that contain that lexical evidence.
        if lexical and max(lexical.values(), default=0.0) >= 0.7:
            candidates = [item for item in candidates if item[2] > 0.0]
        if not candidates:
            return []

        selected = self._select_diverse(candidates, top_k)
        results = []
        for score, semantic_score, keyword_score, chunk in selected:
            result = dict(chunk)
            result["score"] = round(score, 4)
            result["semantic_score"] = round(semantic_score, 4)
            result["keyword_score"] = round(keyword_score, 4)
            results.append(result)
        return results

    def _semantic_scores(
        self,
        query: str,
        chunks: list[dict],
        stored_embeddings: dict[str, bytes],
    ) -> dict[str, float]:
        self._ensure_embeddings()
        if self.embedding_provider is None:
            return {}
        query_embedding = self.embedding_provider.embed(query)
        scores: dict[str, float] = {}
        if stored_embeddings:
            for chunk in chunks:
                vector_blob = stored_embeddings.get(chunk["id"])
                if not vector_blob:
                    continue
                vector = list(struct.unpack(f"{len(vector_blob) // 4}f", vector_blob))
                scores[chunk["id"]] = cosine_similarity(query_embedding, vector)
            return scores

        # Test providers and legacy databases may not have persisted vectors;
        # compute a bounded in-memory candidate set rather than returning the
        # entire document.
        vectors = self.embedding_provider.embed_batch(
            [chunk.get("content", "") for chunk in chunks]
        )
        for chunk, vector in zip(chunks, vectors):
            scores[chunk["id"]] = cosine_similarity(query_embedding, vector)
        return scores

    def _lexical_scores(self, query: str, chunks: list[dict]) -> dict[str, float]:
        query_terms = self._terms(query)
        if not query_terms:
            return {}
        query_lower = " ".join(query.lower().split())
        scores: dict[str, float] = {}
        for chunk in chunks:
            content = chunk.get("content", "")
            content_terms = self._terms(content)
            overlap = query_terms & content_terms
            if not overlap:
                scores[chunk["id"]] = 0.0
                continue
            coverage = len(overlap) / len(query_terms)
            phrase_bonus = 0.12 if query_lower in " ".join(content.lower().split()) else 0.0
            heading = str(chunk.get("metadata", {}).get("heading", ""))
            heading_overlap = overlap & self._terms(heading)
            heading_bonus = 0.22 * len(heading_overlap) / len(query_terms)
            # A matching section heading is strong evidence even when the
            # section body is short (for example, an Appendix URL list).
            heading_floor = min(1.0, 0.82 + heading_bonus) if heading_overlap else 0.0
            # Mild length normalization prevents a giant chunk from winning
            # merely because it contains many repeated words.
            length_penalty = 1.0 / max(1.0, math.log(len(content_terms) + 2, 2) / 8)
            scores[chunk["id"]] = min(
                1.0,
                max(heading_floor, coverage * length_penalty + phrase_bonus + heading_bonus),
            )
        return scores

    @staticmethod
    def _chunk_overlap(left: dict, right: dict) -> float:
        left_terms = RetrievalService._terms(left.get("content", ""))
        right_terms = RetrievalService._terms(right.get("content", ""))
        if not left_terms or not right_terms:
            return 0.0
        return len(left_terms & right_terms) / len(left_terms | right_terms)

    def _select_diverse(
        self,
        candidates: list[tuple[float, float, float, dict]],
        top_k: int,
    ) -> list[tuple[float, float, float, dict]]:
        """Select high-scoring chunks while avoiding near-duplicate overlap."""
        remaining = list(candidates)
        selected: list[tuple[float, float, float, dict]] = []
        while remaining and len(selected) < top_k:
            best_index = 0
            best_value = float("-inf")
            for index, item in enumerate(remaining):
                relevance = item[0]
                redundancy = max(
                    (self._chunk_overlap(item[3], chosen[3]) for chosen in selected),
                    default=0.0,
                )
                mmr_value = 0.78 * relevance - 0.22 * redundancy
                if mmr_value > best_value:
                    best_value = mmr_value
                    best_index = index
            selected.append(remaining.pop(best_index))
        return selected