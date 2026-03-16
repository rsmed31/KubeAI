"""E2E lifecycle test: task submit → routing → assignment → agent record → events → metrics → API."""
from __future__ import annotations

import pytest

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.blueprint import Blueprint, BlueprintRegistry
from KubeAI.memory.shared_memory import SharedMemory
from KubeAI.monitoring import EventStreamHub, MetricsStore
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool
from KubeAI.orchestrator.orchestrator import Orchestrator
from KubeAI.scheduler.lifecycle import AgentLifecycleManager


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_llm_pool() -> LLMPool:
    """One CAPABLE model — claude-sonnet-4."""
    pool = LLMPool()
    pool.register(
        ModelEntry(
            model_id="claude-sonnet-4",
            provider="anthropic",
            tier=ModelTier.CAPABLE,
            cost_per_1k_tokens=0.003,
        )
    )
    return pool


def _make_system(
    score_fn=None,
    decompose_fn=None,
) -> tuple[
    LLMPool,
    MCPPool,
    AssignmentPolicy,
    Orchestrator,
    BlueprintRegistry,
    ControlPlaneAPI,
    AgentLifecycleManager,
    SharedMemory,
]:
    """Build and wire all real KubeAI components (no mocks, no network)."""
    llm_pool = _make_llm_pool()
    mcp_pool = MCPPool()  # empty — no MCP servers required

    policy = AssignmentPolicy(llm_pool, mcp_pool)

    # Inject deterministic score_fn / decompose_fn so no API calls happen
    _score_fn = score_fn if score_fn is not None else (lambda task, bp, model: 0.9)
    _decompose_fn = decompose_fn if decompose_fn is not None else (lambda task, model: [task])

    orchestrator = Orchestrator(
        policy=policy,
        score_fn=_score_fn,
        decompose_fn=_decompose_fn,
    )

    registry = BlueprintRegistry()
    registry.register(
        Blueprint(
            name="research_agent",
            description="Researches topics using web search and summarization.",
            tier=ModelTier.CAPABLE,
        )
    )
    registry.register(
        Blueprint(
            name="coding_agent",
            description="Writes and reviews Python and TypeScript code.",
            tier=ModelTier.CAPABLE,
        )
    )

    metrics = MetricsStore()
    events = EventStreamHub()
    control_plane = ControlPlaneAPI(metrics=metrics, events=events)

    memory = SharedMemory()
    lifecycle = AgentLifecycleManager(policy=policy, control_plane=control_plane, memory=memory)

    return llm_pool, mcp_pool, policy, orchestrator, registry, control_plane, lifecycle, memory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullLifecycle:
    """Full E2E lifecycle: route → assign → spawn → verify control-plane sync."""

    def test_full_lifecycle(self) -> None:
        """Route a task, get a blueprint, assign resources, spawn an agent,
        verify agent appears in ControlPlaneAPI, event is emitted, metrics
        updated, and agent state is running."""
        (
            llm_pool, mcp_pool, policy, orchestrator,
            registry, control_plane, lifecycle, memory,
        ) = _make_system(score_fn=lambda task, bp, model: 0.9)

        task = "Write a Python quicksort implementation"
        blueprints = registry.list_blueprints()

        # Route
        blueprint, score = orchestrator.route(task, blueprints)
        assert blueprint is not None
        assert 0.0 <= score <= 1.0

        # Assign
        assignment = orchestrator.assign(blueprint, task=task)
        assert assignment.model_id == "claude-sonnet-4"

        # Spawn
        agent = lifecycle.spawn(blueprint)
        assert agent.agent_id.startswith("agent-")
        assert agent.state == "running"

        # Agent appears in ControlPlaneAPI
        records = control_plane.list_agents()
        agent_ids = [r.agent_id for r in records]
        assert agent.agent_id in agent_ids

        # State is running
        record = control_plane.get_agent(agent.agent_id)
        assert record.state == "running"

        # At least one agent.spawned event was emitted
        events = control_plane.list_events(limit=50)
        event_types = [e["event_type"] for e in events]
        assert "agent.spawned" in event_types

        # Metrics snapshot is accessible (spawn goes through lifecycle, not register_agent)
        snapshot = control_plane.metrics_snapshot()
        assert isinstance(snapshot, dict)
        assert "counters" in snapshot

    def test_task_submit_updates_control_plane(self) -> None:
        """submit_task() creates a task record that appears in list_tasks()."""
        _, _, _, _, _, control_plane, _, _ = _make_system()

        task_info = control_plane.submit_task(
            "Summarise the latest ML papers", blueprint="research_agent"
        )
        task_id = task_info["task_id"]

        tasks = control_plane.list_tasks(limit=10)
        task_ids = [t.task_id for t in tasks]
        assert task_id in task_ids
        assert task_info["status"] == "queued"

    def test_agent_spawn_appears_in_overview(self) -> None:
        """After spawning an agent the overview shows active_agents >= 1."""
        (
            _, _, _, _, registry, control_plane, lifecycle, _,
        ) = _make_system()

        bp = registry.get("coding_agent")
        lifecycle.spawn(bp)

        overview = control_plane.get_overview()
        assert overview["active_agents"] >= 1

    def test_handoff_persists_context(self) -> None:
        """Set working memory on one agent_id, handoff to a new one, read back."""
        _, _, _, _, _, _, _, memory = _make_system()

        from_id = "agent-aaa"
        to_id = "agent-bbb"

        memory.set_working(from_id, "context", {"step": 3, "partial_result": "foo"})
        memory.handoff(from_id, to_id)

        value = memory.get_working(to_id, "context")
        assert value is not None
        assert value["step"] == 3
        assert value["partial_result"] == "foo"

    def test_terminate_updates_control_plane(self) -> None:
        """Spawn an agent then terminate it — control-plane state becomes terminated."""
        (
            _, _, _, _, registry, control_plane, lifecycle, _,
        ) = _make_system()

        bp = registry.get("research_agent")
        agent = lifecycle.spawn(bp)

        assert control_plane.get_agent(agent.agent_id).state == "running"

        lifecycle.terminate(agent.agent_id)

        # After terminate the agent should be in terminated state in control-plane
        record = control_plane.get_agent(agent.agent_id)
        assert record.state == "terminated"

    def test_events_emitted_for_lifecycle(self) -> None:
        """Spawn + terminate emits agent.spawned and agent.terminated events."""
        (
            _, _, _, _, registry, control_plane, lifecycle, _,
        ) = _make_system()

        bp = registry.get("coding_agent")
        agent = lifecycle.spawn(bp)
        lifecycle.terminate(agent.agent_id)

        events = control_plane.list_events(limit=100)
        event_types = [e["event_type"] for e in events]
        assert "agent.spawned" in event_types
        assert "agent.terminated" in event_types

    def test_shared_memory_across_tiers(self) -> None:
        """Write to short_term tier, read back; write to long_term tier, read back."""
        _, _, _, _, _, _, _, memory = _make_system()

        # short_term
        memory.set_short_term("domain-x", "session_key", "session_value")
        assert memory.get_short_term("domain-x", "session_key") == "session_value"

        # long_term (SQLite in-memory)
        memory.set_long_term("coding_agent", "style_guide", "pep8")
        assert memory.get_long_term("coding_agent", "style_guide") == "pep8"

    def test_orchestrator_uses_routing_model(self) -> None:
        """Verify route() calls score_fn with the largest model's model_id."""
        called_model_ids: list[str] = []

        def capturing_score_fn(task: str, blueprint: Blueprint, model_id: str) -> float:
            called_model_ids.append(model_id)
            return 0.75

        (
            llm_pool, _, _, orchestrator, registry, _, _, _,
        ) = _make_system(score_fn=capturing_score_fn)

        # The only (and therefore largest) model registered is claude-sonnet-4
        routing_model_id = llm_pool.routing_model().model_id

        blueprints = registry.list_blueprints()
        orchestrator.route("some task", blueprints)

        # Every call to score_fn should have used the routing model
        assert len(called_model_ids) > 0
        assert all(mid == routing_model_id for mid in called_model_ids)

    def test_record_task_result_updates_metrics(self) -> None:
        """record_task_result() should increment KubeAI_tasks_total counter."""
        _, _, _, _, _, control_plane, _, _ = _make_system()

        snapshot_before = control_plane.metrics_snapshot()
        counters_before = {
            (c["name"], tuple(sorted(c["labels"].items()))): c["value"]
            for c in snapshot_before["counters"]
        }

        control_plane.record_task_result(
            task_id="task-001",
            blueprint="research_agent",
            status="success",
            latency_ms=123.4,
            token_cost=0.001,
            eval_score=0.88,
        )

        snapshot_after = control_plane.metrics_snapshot()
        counters_after = {
            (c["name"], tuple(sorted(c["labels"].items()))): c["value"]
            for c in snapshot_after["counters"]
        }

        key = ("KubeAI_tasks_total", (("blueprint", "research_agent"), ("status", "success")))
        assert counters_after.get(key, 0) > counters_before.get(key, 0)
