"""Unit tests for KnowledgeGraphRAG entity/relation extraction and graph serialization."""

from __future__ import annotations

from dataclasses import dataclass

from KubeAI.templates.rag.knowledge_graph import KnowledgeGraphRAG


@dataclass
class _Agent:
    """Simple attach target for template tests."""


class TestKnowledgeGraphRAG:
    def test_attach_and_entity_extraction(self) -> None:
        rag = KnowledgeGraphRAG(max_nodes=50, max_edges=50)
        agent = _Agent()
        rag.attach(agent, {"max_nodes": 50, "max_edges": 50})

        assert getattr(agent, "rag_template") is rag

        entities = rag.extract_entities("KubeAI Orchestrator uses Redis memory tier")
        assert "KubeAI Orchestrator" in entities
        assert any(entity.lower() == "redis" for entity in entities)

    def test_add_documents_extracts_relations_and_serializes_graph(self) -> None:
        rag = KnowledgeGraphRAG(max_nodes=100, max_edges=100)
        rag.add_documents(
            [
                "KubeAI Orchestrator uses Redis for short-term memory.",
                "Scheduler routes Agent tasks to Orchestrator.",
                "Agent calls MCP tools for retrieval.",
            ]
        )

        graph = rag.serialize_graph()
        assert graph["nodes"]
        assert graph["edges"]
        assert any(edge["predicate"] in {"uses", "routes_to", "calls"} for edge in graph["edges"])

    def test_retrieve_and_neighbors(self) -> None:
        rag = KnowledgeGraphRAG(max_nodes=100, max_edges=100)
        rag.add_documents(
            [
                "KubeAI Orchestrator uses Redis for context storage.",
                "KubeAI Orchestrator uses SQLite for long term memory.",
                "Scheduler routes tasks to KubeAI Orchestrator.",
            ]
        )

        retrieved = rag.retrieve("How does KubeAI use Redis", top_k=2)
        assert retrieved
        assert len(retrieved) <= 2
        assert any("Redis" in relation for relation in retrieved)

        neighbors = rag.neighbors("KubeAI Orchestrator", top_k=3)
        assert neighbors
        assert len(neighbors) <= 3

    def test_max_nodes_and_edges_limits(self) -> None:
        rag = KnowledgeGraphRAG(max_nodes=2, max_edges=2)
        rag.add_documents(
            [
                "Alpha uses Beta.",
                "Gamma uses Delta.",
                "Epsilon uses Zeta.",
            ]
        )

        graph = rag.serialize_graph()
        assert len(graph["nodes"]) <= 2
        assert len(graph["edges"]) <= 2
