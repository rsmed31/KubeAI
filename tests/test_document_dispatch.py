"""Unit tests for direct document dispatch and scheduler module policy lane components."""

from __future__ import annotations

import pytest

from KubeAI.orchestrator.a2a_pool import A2AAgentCard, A2APool
from KubeAI.orchestrator.a2a_router import A2ARouter
from KubeAI.orchestrator.document_dispatch import DocumentDispatcher
from KubeAI.orchestrator.document_probe import DocumentProbe
from KubeAI.scheduler.module_policy import ModulePolicyError, SchedulerModulePolicy


def _pool_with_rag_agent() -> A2APool:
    pool = A2APool()
    pool.register(
        A2AAgentCard(
            agent_id="agent-rag",
            name="agent-rag",
            endpoint="http://localhost/agent-rag",
            capabilities=frozenset({"rag_retrieval", "fetch_url", "knowledge_graph"}),
        )
    )
    return pool


class TestDocumentProbe:
    def test_probe_samples_and_infers_capabilities(self) -> None:
        probe = DocumentProbe(sample_chars=80, preview_chars=30)
        document = "This URL https://example.com contains JSON tables and graph entities for KubeAI."

        result = probe.probe(document)
        assert len(result.sample) <= 80
        assert len(result.preview) <= 30
        assert result.estimated_tokens > 0
        assert "rag_retrieval" in result.required_capabilities
        assert "fetch_url" in result.required_capabilities
        assert "data_processing" in result.required_capabilities

    def test_probe_empty_document_raises(self) -> None:
        probe = DocumentProbe()
        with pytest.raises(ValueError, match="empty"):
            probe.probe("   ")


class TestSchedulerModulePolicy:
    def test_agent_override_beats_global_setting(self) -> None:
        policy = SchedulerModulePolicy(default_enabled=True)
        policy.disable("rag_retrieval")
        policy.enable("rag_retrieval", agent_id="agent-rag")

        assert policy.is_enabled("rag_retrieval", agent_id="agent-rag") is True
        assert policy.is_enabled("rag_retrieval", agent_id="other-agent") is False

    def test_assert_enabled_raises_for_disabled_modules(self) -> None:
        policy = SchedulerModulePolicy(default_enabled=True)
        policy.disable("document_dispatch", agent_id="agent-rag")

        with pytest.raises(ModulePolicyError, match="document_dispatch"):
            policy.assert_enabled(["document_dispatch", "rag_retrieval"], agent_id="agent-rag")


class TestDocumentDispatcher:
    def test_dispatch_routes_document_and_payload(self) -> None:
        pool = _pool_with_rag_agent()
        router = A2ARouter(pool)
        dispatcher = DocumentDispatcher(router)

        document = "Fetch this URL and summarize graph entities for KubeAI: https://example.com/doc"
        result = dispatcher.dispatch("Summarize the document", document)

        assert result.dispatch_id.startswith("dispatch-")
        assert result.routed_task.target.agent_id == "agent-rag"
        assert "rag_retrieval" in result.routed_task.required_capabilities
        assert "fetch_url" in result.routed_task.required_capabilities
        assert "document_preview" in result.routed_task.payload
        assert result.routed_task.payload["document"] == document

        dispatcher.complete(result)
        connections = pool.list_connections()
        assert connections
        assert connections[0].reuse_count == 0

    def test_dispatch_respects_module_policy(self) -> None:
        pool = _pool_with_rag_agent()
        router = A2ARouter(pool)
        policy = SchedulerModulePolicy(default_enabled=True)
        policy.disable("document_dispatch", agent_id="agent-rag")
        dispatcher = DocumentDispatcher(router, module_policy=policy)

        with pytest.raises(ModulePolicyError, match="document_dispatch"):
            dispatcher.dispatch(
                "Summarize the document",
                "KubeAI routes document tasks through A2A with RAG retrieval.",
            )

        # Failed dispatch should release the leased connection.
        connections = pool.list_connections()
        assert connections
        assert connections[0].reuse_count == 0
