"""Integration tests for orchestrator direct-document flow with probe, spawn, RAG readiness, and run status events."""

from __future__ import annotations

from dataclasses import dataclass

from KubeAI.blueprint import Blueprint
from KubeAI.orchestrator.a2a_pool import A2APool
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool, MCPServer
from KubeAI.orchestrator.orchestrator import Orchestrator, RunStatusEvent


def _make_policy() -> AssignmentPolicy:
    llm = LLMPool()
    llm.register(ModelEntry("model-fast", "test", ModelTier.FAST, 0.001))
    llm.register(ModelEntry("model-capable", "test", ModelTier.CAPABLE, 0.003))
    llm.register(ModelEntry("model-best", "test", ModelTier.BEST, 0.010))

    mcp = MCPPool()
    mcp.register(
        MCPServer(
            server_id="web",
            endpoint="http://mcp/web",
            capabilities=frozenset({"fetch_url", "web_search"}),
        )
    )
    mcp.register(
        MCPServer(
            server_id="data",
            endpoint="http://mcp/data",
            capabilities=frozenset({"data_processing"}),
        )
    )
    return AssignmentPolicy(llm, mcp)


@dataclass
class _SpawnRecorder:
    agent_id: str = "agent-spawned-1"
    called: bool = False
    metadata: dict[str, object] | None = None

    def __call__(self, blueprint: Blueprint, assignment, metadata: dict[str, object]) -> str:
        self.called = True
        self.metadata = dict(metadata)
        return self.agent_id


class TestOrchestratorDocumentRun:
    def test_big_document_spawns_scraper_rag_agent_and_dispatches_with_status(self) -> None:
        policy = _make_policy()

        blueprint = Blueprint(
            name="research_agent",
            description="Handles document analysis and retrieval-heavy tasks.",
            tier=ModelTier.CAPABLE,
            required_capabilities=frozenset({"web_search"}),
        )

        statuses: list[RunStatusEvent] = []
        spawn = _SpawnRecorder()
        pool = A2APool()

        orch = Orchestrator(
            policy=policy,
            score_fn=lambda task, bp, model_id: 0.95,
        )

        large_document = (
            "KubeAI architecture includes orchestrator routing, scheduler reuse, "
            "A2A messaging, and RAG retrieval with URL ingestion. "
        ) * 120

        result = orch.orchestrate_document_run(
            task="Analyze architecture risks and summarize findings.",
            document=large_document,
            blueprints=[blueprint],
            a2a_pool=pool,
            spawn_agent_fn=spawn,
            status_callback=statuses.append,
            long_doc_token_threshold=120,
        )

        assert spawn.called is True
        assert spawn.metadata is not None
        assert spawn.metadata["rag_template"] == "scraper"

        assert result.rag_template == "scraper"
        assert result.agent_id == "agent-spawned-1"
        assert [server.server_id for server in result.assignment.mcp_servers] == ["web"]
        assert result.dispatch.routed_task.target.agent_id == "agent-spawned-1"
        assert blueprint.description in result.dispatch.routed_task.target.description
        assert "rag=scraper" in result.dispatch.routed_task.target.description
        assert "mcps=web" in result.dispatch.routed_task.target.description
        assert result.dispatch.routed_task.payload["document"] == large_document
        assert result.dispatch.routed_task.payload["document_preview"]
        assert result.dispatch.routed_task.payload["agent_id"] == "agent-spawned-1"

        event_stages = [event.stage for event in result.events]
        assert event_stages == [
            "probe_document",
            "route_blueprint",
            "assign_resources",
            "spawn_agent",
            "dispatch_document",
            "completed",
        ]
        assert [event.stage for event in statuses] == event_stages

    def test_small_document_prefers_basic_rag_template(self) -> None:
        policy = _make_policy()
        blueprint = Blueprint(
            name="general_agent",
            description="General routing target.",
            tier=ModelTier.FAST,
        )

        pool = A2APool()
        spawn = _SpawnRecorder(agent_id="agent-small-1")
        orch = Orchestrator(policy=policy, score_fn=lambda task, bp, model_id: 0.80)

        small_document = "Short note about KubeAI routing."
        result = orch.orchestrate_document_run(
            task="Summarize note",
            document=small_document,
            blueprints=[blueprint],
            a2a_pool=pool,
            spawn_agent_fn=spawn,
            long_doc_token_threshold=200,
        )

        assert result.rag_template == "basic"
        assert spawn.metadata is not None
        assert spawn.metadata["rag_template"] == "basic"
        assert result.assignment.mcp_servers == ()
        assert result.dispatch.probe.estimated_tokens > 0

    def test_spawn_callback_without_id_gets_generated_tracking_id(self) -> None:
        policy = _make_policy()
        blueprint = Blueprint(
            name="tracker_agent",
            description="Tracking-focused route target.",
            tier=ModelTier.FAST,
        )

        pool = A2APool()
        spawn = _SpawnRecorder(agent_id="   ")
        orch = Orchestrator(policy=policy, score_fn=lambda task, bp, model_id: 0.65)

        result = orch.orchestrate_document_run(
            task="Summarize tracking metadata",
            document="short doc",
            blueprints=[blueprint],
            a2a_pool=pool,
            spawn_agent_fn=spawn,
        )

        assert result.agent_id.startswith("agent-")
        assert result.dispatch.routed_task.target.agent_id == result.agent_id
        assert result.dispatch.routed_task.payload["agent_id"] == result.agent_id
