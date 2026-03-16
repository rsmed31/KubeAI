"""Hybrid RAG is the service-mesh analogue that fuses multiple retrieval signals before routing context."""

from __future__ import annotations

from typing import Any, Iterable, MutableMapping

import numpy as np

from KubeAI.templates.base import Template
from KubeAI.templates.rag.vectorizer import (
    build_vector_index,
    cosine_similarity_matrix,
    text_to_vector,
    tokenize,
)

try:  # pragma: no cover - optional library fallback
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - optional library fallback
    BM25Okapi = None


class HybridRAG(Template):
    """Hybrid retrieval combining BM25 keyword search and vector similarity with RRF."""

    def __init__(self) -> None:
        super().__init__(name="hybrid")
        self._vector_dim = 256
        self._documents: list[str] = []
        self._tokenized_docs: list[list[str]] = []
        self._vectors = np.empty((0, self._vector_dim), dtype=np.float32)
        self._bm25: BM25Okapi | None = None
        self._config: dict[str, Any] = {
            "bm25_weight": 0.5,
            "vector_weight": 0.5,
            "rrf_k": 60,
            "top_k": 5,
            "similarity_threshold": 0.0,
            "vector_dim": self._vector_dim,
        }

    def __repr__(self) -> str:
        return (
            f"HybridRAG(documents={len(self._documents)}, "
            f"weights=({self._config.get('bm25_weight')}, {self._config.get('vector_weight')}), "
            f"rrf_k={self._config.get('rrf_k')})"
        )

    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        merged = dict(self._config)
        merged.update(dict(config or {}))
        self._config = merged
        self._vector_dim = max(8, int(self._config.get("vector_dim", self._vector_dim)))
        self._rebuild_indexes()
        setattr(agent, "rag_template", self)

    def add_documents(self, docs: Iterable[str]) -> None:
        added = False
        for doc in docs:
            if doc:
                self._documents.append(doc)
                self._tokenized_docs.append(tokenize(doc))
                added = True
        if added:
            self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        self._vectors = build_vector_index(self._documents, dim=self._vector_dim)
        if BM25Okapi is not None and self._tokenized_docs:
            self._bm25 = BM25Okapi(self._tokenized_docs)
        else:
            self._bm25 = None

    def _bm25_scores(self, query_tokens: list[str]) -> np.ndarray:
        if not self._documents:
            return np.array([], dtype=np.float32)

        if self._bm25 is not None:
            return np.asarray(self._bm25.get_scores(query_tokens), dtype=np.float32)

        query_set = set(query_tokens)
        fallback = []
        for doc_tokens in self._tokenized_docs:
            if not doc_tokens:
                fallback.append(0.0)
                continue
            overlap = len(query_set.intersection(doc_tokens))
            fallback.append(float(overlap) / float(len(doc_tokens)))
        return np.asarray(fallback, dtype=np.float32)

    @staticmethod
    def _rank_positions(scores: np.ndarray) -> np.ndarray:
        order = np.argsort(-scores, kind="stable")
        ranks = np.empty(order.shape[0], dtype=np.int32)
        ranks[order] = np.arange(1, order.shape[0] + 1)
        return ranks

    def retrieve_with_scores(
        self,
        query: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[tuple[str, float]]:
        """Return top-k documents with reciprocal-rank-fusion scores."""
        if not query or not self._documents:
            return []

        limit = max(1, int(top_k if top_k is not None else self._config.get("top_k", 5)))
        threshold = float(
            self._config.get("similarity_threshold", 0.0)
            if similarity_threshold is None
            else similarity_threshold
        )

        query_tokens = tokenize(query)
        bm25_scores = self._bm25_scores(query_tokens)
        vector_scores = cosine_similarity_matrix(
            self._vectors,
            text_to_vector(query, dim=self._vector_dim),
        )

        bm25_ranks = self._rank_positions(bm25_scores)
        vector_ranks = self._rank_positions(vector_scores)

        rrf_k = float(self._config.get("rrf_k", 60))
        bm25_weight = float(self._config.get("bm25_weight", 0.5))
        vector_weight = float(self._config.get("vector_weight", 0.5))

        fused_scores = (
            bm25_weight / (rrf_k + bm25_ranks.astype(np.float32))
            + vector_weight / (rrf_k + vector_ranks.astype(np.float32))
        )

        ranked = sorted(
            (
                (idx, float(score))
                for idx, score in enumerate(fused_scores)
                if float(score) >= threshold
            ),
            key=lambda item: (-item[1], item[0]),
        )
        return [(self._documents[idx], score) for idx, score in ranked[:limit]]

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        if top_k <= 0:
            return []
        return [doc for doc, _ in self.retrieve_with_scores(query=query, top_k=top_k)]
