"""Unit tests for custom A2A pool and router lane components."""

from __future__ import annotations

import pytest

from KubeAI.orchestrator.a2a_pool import A2AAgentCard, A2APool
from KubeAI.orchestrator.a2a_router import A2ARouter


def _card(agent_id: str, *capabilities: str, load: float = 0.0, healthy: bool = True) -> A2AAgentCard:
    return A2AAgentCard(
        agent_id=agent_id,
        name=agent_id,
        endpoint=f"http://localhost/{agent_id}",
        capabilities=frozenset(capabilities),
        load=load,
        healthy=healthy,
    )


class TestA2APool:
    def test_select_prefers_healthy_capability_match(self) -> None:
        pool = A2APool()
        pool.register(_card("agent-a", "rag_retrieval", "fetch_url", load=0.2))
        pool.register(_card("agent-b", "rag_retrieval", "fetch_url", load=0.1, healthy=False))
        pool.register(_card("agent-c", "rag_retrieval", load=0.6))

        chosen = pool.select(required_capabilities=["rag_retrieval", "fetch_url"])
        assert chosen.agent_id == "agent-a"

    def test_select_missing_capability_raises(self) -> None:
        pool = A2APool()
        pool.register(_card("agent-a", "rag_retrieval"))

        with pytest.raises(ValueError, match="capabilities"):
            pool.select(required_capabilities=["db_query"])

    def test_acquire_connection_reuses_same_id(self) -> None:
        pool = A2APool()
        pool.register(_card("agent-a", "rag_retrieval"))

        first = pool.acquire_connection("agent-a")
        second = pool.acquire_connection("agent-a")

        assert first.connection_id == second.connection_id
        assert first.reuse_count == 1
        assert second.reuse_count == 2

    def test_preferred_agent_used_when_not_overloaded(self) -> None:
        pool = A2APool()
        pool.register(_card("agent-a", "rag_retrieval", load=0.2))
        pool.register(_card("agent-b", "rag_retrieval", load=0.1))

        chosen = pool.select(
            required_capabilities=["rag_retrieval"],
            preferred_agent_id="agent-a",
        )
        assert chosen.agent_id == "agent-a"


class TestA2ARouter:
    def test_route_and_complete_releases_connection(self) -> None:
        pool = A2APool()
        pool.register(_card("agent-rag", "rag_retrieval", "fetch_url"))
        router = A2ARouter(pool)

        routed = router.route(
            "Summarize this document",
            required_capabilities=["rag_retrieval", "fetch_url"],
            payload={"source": "unit-test"},
        )

        assert routed.target.agent_id == "agent-rag"
        assert routed.connection.reuse_count == 1
        assert "fetch_url" in routed.required_capabilities
        assert routed.payload["source"] == "unit-test"

        router.complete(routed)
        connections = pool.list_connections()
        assert connections
        assert connections[0].reuse_count == 0

    def test_route_empty_task_raises(self) -> None:
        pool = A2APool()
        pool.register(_card("agent-rag", "rag_retrieval"))
        router = A2ARouter(pool)

        with pytest.raises(ValueError, match="empty"):
            router.route("   ")
