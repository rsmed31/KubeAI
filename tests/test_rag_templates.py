"""Unit tests for RAG template variants: basic, hybrid, and reranking."""

from __future__ import annotations

from dataclasses import dataclass

from KubeAI.templates.rag.basic import BasicRAG
from KubeAI.templates.rag.hybrid import HybridRAG
from KubeAI.templates.rag.reranking import RerankingRAG


@dataclass
class _Agent:
    """Simple attach target for template tests."""


DOCS = [
    "python decorators and function wrappers",
    "kubernetes scheduler assigns pods to nodes",
    "bread baking starter hydration technique",
]


class TestBasicRAG:
    def test_add_documents_and_retrieve(self) -> None:
        rag = BasicRAG()
        rag.attach(_Agent(), {"top_k": 2, "similarity_threshold": 0.0})
        rag.add_documents(DOCS)

        results = rag.retrieve("python function decorators", top_k=2)
        assert len(results) <= 2
        assert results
        assert "python" in results[0]

    def test_threshold_and_empty_paths(self) -> None:
        rag = BasicRAG()
        rag.attach(_Agent(), {"top_k": 3, "similarity_threshold": 0.95})
        rag.add_documents(DOCS)

        assert rag.retrieve("", top_k=3) == []
        # Exact text should pass high threshold.
        exact = rag.retrieve(DOCS[0], top_k=3)
        assert exact
        assert DOCS[0] == exact[0]


class TestHybridRAG:
    def test_hybrid_retrieval_prefers_lexical_match(self) -> None:
        rag = HybridRAG()
        rag.attach(_Agent(), {"top_k": 3, "similarity_threshold": 0.0})
        rag.add_documents(DOCS)

        results = rag.retrieve("scheduler pods nodes", top_k=2)
        assert results
        assert "scheduler" in results[0]

    def test_retrieve_with_scores_is_sorted(self) -> None:
        rag = HybridRAG()
        rag.attach(_Agent(), {"top_k": 5, "rrf_k": 30})
        rag.add_documents(DOCS)

        scored = rag.retrieve_with_scores("python wrappers", top_k=3)
        assert scored
        assert len(scored) <= 3
        scores = [score for _, score in scored]
        assert scores == sorted(scores, reverse=True)


class TestRerankingRAG:
    def test_reranking_fallback_respects_post_top_k(self) -> None:
        rag = RerankingRAG()
        rag.attach(
            _Agent(),
            {
                "reranker_model": "fallback-lexical",
                "pre_rerank_top_k": 3,
                "post_rerank_top_k": 1,
            },
        )
        rag.add_documents(DOCS)

        results = rag.retrieve("python function wrappers", top_k=3)
        assert len(results) == 1
        assert "python" in results[0]

    def test_reranking_is_deterministic(self) -> None:
        rag = RerankingRAG()
        rag.attach(_Agent(), {"reranker_model": "fallback-lexical"})
        rag.add_documents(DOCS)

        first = rag.retrieve("kubernetes scheduler", top_k=2)
        second = rag.retrieve("kubernetes scheduler", top_k=2)
        assert first == second
