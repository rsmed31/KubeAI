"""Tests for EvalController automatic underperformer replacement loop."""

from __future__ import annotations

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.blueprint import Blueprint
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool
from KubeAI.scheduler import AgentLifecycleManager, EvalController


def _make_lifecycle() -> tuple[AgentLifecycleManager, ControlPlaneAPI, Blueprint]:
    llm_pool = LLMPool()
    llm_pool.register(
        ModelEntry(
            model_id="claude-sonnet-4",
            provider="anthropic",
            tier=ModelTier.CAPABLE,
            cost_per_1k_tokens=0.003,
        )
    )
    mcp_pool = MCPPool()
    policy = AssignmentPolicy(llm_pool, mcp_pool)
    control_plane = ControlPlaneAPI()

    lifecycle = AgentLifecycleManager(policy=policy, control_plane=control_plane)
    blueprint = Blueprint(
        name="research_agent",
        description="Research blueprint",
        tier=ModelTier.CAPABLE,
    )
    return lifecycle, control_plane, blueprint


class TestEvalController:
    def test_replaces_underperforming_agents(self) -> None:
        lifecycle, control_plane, blueprint = _make_lifecycle()

        bad_agent = lifecycle.spawn(blueprint)
        _good_agent = lifecycle.spawn(blueprint)

        def score_fn(agent) -> float:  # type: ignore[no-untyped-def]
            return 0.2 if agent.agent_id == bad_agent.agent_id else 0.9

        controller = EvalController(
            lifecycle=lifecycle,
            control_plane=control_plane,
            score_fn=score_fn,
            min_score=0.6,
        )

        before = {agent.agent_id for agent in lifecycle.list_agents()}
        decisions = controller.run_once()
        after = {agent.agent_id for agent in lifecycle.list_agents()}

        assert len(decisions) == 2
        assert any(decision.replaced for decision in decisions)
        assert bad_agent.agent_id not in after
        assert len(after) == len(before)

        events = control_plane.list_events(limit=200)
        event_types = [event["event_type"] for event in events]
        assert "agent.eval_replaced" in event_types

    def test_does_not_replace_when_scores_are_healthy(self) -> None:
        lifecycle, control_plane, blueprint = _make_lifecycle()
        lifecycle.spawn(blueprint)

        controller = EvalController(
            lifecycle=lifecycle,
            control_plane=control_plane,
            score_fn=lambda _agent: 0.91,
            min_score=0.6,
        )

        decisions = controller.run_once()

        assert len(decisions) == 1
        assert decisions[0].replaced is False

        snapshot = control_plane.metrics_snapshot()
        eval_histograms = [
            entry
            for entry in snapshot["histograms"]
            if entry["name"] == "KubeAI_eval_score"
        ]
        assert eval_histograms
