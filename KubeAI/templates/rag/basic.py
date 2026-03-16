"""Basic RAG is the ConfigMap-like analogue for injecting top-k context before agent execution."""

from __future__ import annotations

from typing import Any, Iterable, MutableMapping

import numpy as np

from KubeAI.templates.base import Template
from KubeAI.templates.rag.vectorizer import build_vector_index, cosine_similarity_matrix, text_to_vector


class BasicRAG(Template):
    """Simple deterministic vector retrieval with cosine similarity scoring."""

    def __init__(self) -> None:
        super().__init__(name="basic")
        self._vector_dim = 256
        self._documents: list[str] = []
        self._vectors = np.empty((0, self._vector_dim), dtype=np.float32)
        self._config: dict[str, Any] = {
            "top_k": 3,
            "similarity_threshold": 0.0,
            "vector_dim": self._vector_dim,
        }

    def __repr__(self) -> str:
        return (
            f"BasicRAG(documents={len(self._documents)}, "
            f"vector_dim={self._vector_dim}, "
            f"top_k={self._config.get('top_k')}, "
            f"threshold={self._config.get('similarity_threshold')})"
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
        self._vectors = build_vector_index(self._documents, dim=self._vector_dim)
        setattr(agent, "rag_template", self)

    def add_documents(self, docs: Iterable[str]) -> None:
        added = False
        for doc in docs:
            if doc:
                self._documents.append(doc)
                added = True
        if added:
            self._vectors = build_vector_index(self._documents, dim=self._vector_dim)

    def retrieve_with_scores(
        self,
        query: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[tuple[str, float]]:
        """Return top-k documents with cosine similarity scores."""
        if not query or not self._documents:
            return []

        limit = max(1, int(top_k if top_k is not None else self._config.get("top_k", 3)))
        threshold = float(
            self._config.get("similarity_threshold", 0.0)
            if similarity_threshold is None
            else similarity_threshold
        )

        query_vector = text_to_vector(query, dim=self._vector_dim)
        scores = cosine_similarity_matrix(self._vectors, query_vector)

        ranked = sorted(
            (
                (idx, float(score))
                for idx, score in enumerate(scores)
                if float(score) >= threshold
            ),
            key=lambda item: (-item[1], item[0]),
        )
        return [(self._documents[idx], score) for idx, score in ranked[:limit]]

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        if top_k <= 0:
            return []
        return [doc for doc, _ in self.retrieve_with_scores(query=query, top_k=top_k)]
