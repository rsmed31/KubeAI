"""Reranking RAG is the admission-controller analogue that reorders retrieved context for final quality."""

from __future__ import annotations

from typing import Any, Iterable, MutableMapping

import numpy as np

from KubeAI.templates.base import Template
from KubeAI.templates.rag.hybrid import HybridRAG
from KubeAI.templates.rag.vectorizer import tokenize

try:  # pragma: no cover - optional dependency
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover - optional dependency
    CrossEncoder = None


class RerankingRAG(Template):
    """Second-stage reranking with optional cross-encoder and lexical fallback."""

    def __init__(self) -> None:
        super().__init__(name="reranking")
        self._hybrid = HybridRAG()
        self._cross_encoder: Any | None = None
        self._cross_encoder_unavailable = False
        self._config: dict[str, Any] = {
            "pre_rerank_top_k": 10,
            "post_rerank_top_k": 3,
            "reranker_model": "fallback-lexical",
            "similarity_threshold": 0.0,
        }

    def __repr__(self) -> str:
        return (
            "RerankingRAG(" 
            f"pre={self._config.get('pre_rerank_top_k')}, "
            f"post={self._config.get('post_rerank_top_k')}, "
            f"model={self._config.get('reranker_model')!r})"
        )

    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        merged = dict(self._config)
        merged.update(dict(config or {}))
        self._config = merged

        hybrid_keys = {
            "bm25_weight",
            "vector_weight",
            "rrf_k",
            "top_k",
            "similarity_threshold",
            "vector_dim",
        }
        hybrid_config = {
            key: value
            for key, value in merged.items()
            if key in hybrid_keys
        }

        self._hybrid.attach(agent=agent, config=hybrid_config)
        self._cross_encoder = None
        self._cross_encoder_unavailable = False
        setattr(agent, "rag_template", self)

    def add_documents(self, docs: Iterable[str]) -> None:
        self._hybrid.add_documents(docs)

    def _ensure_cross_encoder(self) -> Any | None:
        model_name = str(self._config.get("reranker_model", "fallback-lexical"))
        if model_name == "fallback-lexical":
            return None
        if self._cross_encoder_unavailable:
            return None
        if self._cross_encoder is not None:
            return self._cross_encoder

        if CrossEncoder is None:
            self._cross_encoder_unavailable = True
            return None

        try:  # pragma: no cover - model loading is environment-dependent
            self._cross_encoder = CrossEncoder(model_name)
        except Exception:
            self._cross_encoder_unavailable = True
            self._cross_encoder = None
        return self._cross_encoder

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        query_tokens = set(tokenize(query))
        text_tokens = set(tokenize(text))
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = len(query_tokens.intersection(text_tokens))
        union = len(query_tokens.union(text_tokens))
        if union == 0:
            return 0.0
        return float(overlap) / float(union)

    def _rerank_scores(self, query: str, docs: list[str]) -> np.ndarray:
        if not docs:
            return np.array([], dtype=np.float32)

        model = self._ensure_cross_encoder()
        if model is None:
            return np.asarray([self._lexical_score(query, doc) for doc in docs], dtype=np.float32)

        pairs = [(query, doc) for doc in docs]
        try:  # pragma: no cover - model execution is environment-dependent
            scores = model.predict(pairs)
            return np.asarray(scores, dtype=np.float32)
        except Exception:
            self._cross_encoder_unavailable = True
            return np.asarray([self._lexical_score(query, doc) for doc in docs], dtype=np.float32)

    def retrieve_with_scores(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[tuple[str, float]]:
        """Return top-k reranked documents with second-stage scores."""
        if not query:
            return []

        pre_top_k = max(1, int(self._config.get("pre_rerank_top_k", 10)))
        candidates = self._hybrid.retrieve_with_scores(
            query=query,
            top_k=pre_top_k,
            similarity_threshold=0.0,
        )
        if not candidates:
            return []

        docs = [doc for doc, _ in candidates]
        first_stage_scores = np.asarray([score for _, score in candidates], dtype=np.float32)
        second_stage_scores = self._rerank_scores(query=query, docs=docs)

        threshold = float(self._config.get("similarity_threshold", 0.0))
        ranked = sorted(
            (
                (idx, float(score), float(first_stage_scores[idx]))
                for idx, score in enumerate(second_stage_scores)
                if float(score) >= threshold
            ),
            key=lambda item: (-item[1], -item[2], item[0]),
        )

        post_top_k = max(1, int(self._config.get("post_rerank_top_k", 3)))
        limit = post_top_k
        if top_k is not None:
            limit = max(1, min(limit, int(top_k)))

        return [(docs[idx], score) for idx, score, _ in ranked[:limit]]

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        if top_k <= 0:
            return []
        return [doc for doc, _ in self.retrieve_with_scores(query=query, top_k=top_k)]
