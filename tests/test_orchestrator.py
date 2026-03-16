"""Unit tests for Orchestrator and Blueprint/BlueprintRegistry (Lane F)."""

from __future__ import annotations

import pytest

from KubeAI.blueprint import Blueprint, BlueprintRegistry
from KubeAI.orchestrator.assignment import Assignment, AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool, MCPServer
from KubeAI.orchestrator.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy(
    *,
    tiers: list[ModelTier] | None = None,
    with_mcp: bool = False,
) -> AssignmentPolicy:
    """Return a minimal AssignmentPolicy populated for testing."""
    pool = LLMPool()
    if tiers is None:
        tiers = [ModelTier.FAST, ModelTier.CAPABLE, ModelTier.BEST]
    for i, tier in enumerate(tiers):
        pool.register(
            ModelEntry(
                model_id=f"model-{tier.value}",
                provider="test-provider",
                tier=tier,
                cost_per_1k_tokens=float(i + 1) * 0.01,
            )
        )
    mcp = MCPPool()
    if with_mcp:
        mcp.register(
            MCPServer(
                server_id="search-server",
                endpoint="http://mcp/search",
                capabilities=frozenset({"search"}),
            )
        )
    return AssignmentPolicy(pool, mcp)


def _make_blueprint(
    name: str = "bp",
    tier: ModelTier = ModelTier.FAST,
    capabilities: frozenset[str] | None = None,
) -> Blueprint:
    return Blueprint(
        name=name,
        description=f"Agent blueprint: {name}",
        tier=tier,
        required_capabilities=capabilities or frozenset(),
    )


def _fixed_score(scores: dict[str, float]) -> object:
    """Return a score_fn that returns predetermined scores by blueprint name."""

    def _fn(task: str, blueprint: Blueprint, model_id: str) -> float:
        return scores.get(blueprint.name, 0.0)

    return _fn


def _fixed_decompose(subtasks: list[str]) -> object:
    """Return a decompose_fn that always returns the given subtasks."""

    def _fn(task: str, model_id: str) -> list[str]:
        return list(subtasks)

    return _fn


# ---------------------------------------------------------------------------
# Blueprint tests
# ---------------------------------------------------------------------------


class TestBlueprint:
    def test_blueprint_is_immutable(self) -> None:
        bp = _make_blueprint()
        with pytest.raises((AttributeError, TypeError)):
            bp.name = "new-name"  # type: ignore[misc]

    def test_blueprint_repr_contains_name_tier_version(self) -> None:
        bp = Blueprint(
            name="coder",
            description="A coding agent",
            tier=ModelTier.CAPABLE,
            version="2.0",
            required_capabilities=frozenset({"code", "debug"}),
        )
        r = repr(bp)
        assert "coder" in r
        assert "capable" in r
        assert "2.0" in r
        # capabilities should be sorted
        assert "['code', 'debug']" in r

    def test_blueprint_default_version(self) -> None:
        bp = _make_blueprint()
        assert bp.version == "1.0"

    def test_blueprint_required_capabilities_is_frozenset(self) -> None:
        bp = _make_blueprint(capabilities=frozenset({"a", "b"}))
        assert isinstance(bp.required_capabilities, frozenset)


class TestBlueprintRegistry:
    def test_register_and_get(self) -> None:
        reg = BlueprintRegistry()
        bp = _make_blueprint("research")
        reg.register(bp)
        assert reg.get("research") is bp

    def test_get_missing_raises_key_error(self) -> None:
        reg = BlueprintRegistry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_register_replaces_existing(self) -> None:
        reg = BlueprintRegistry()
        bp1 = Blueprint(name="agent", description="v1", tier=ModelTier.FAST)
        bp2 = Blueprint(name="agent", description="v2", tier=ModelTier.BEST)
        reg.register(bp1)
        reg.register(bp2)
        assert reg.get("agent").description == "v2"

    def test_list_blueprints_returns_all(self) -> None:
        reg = BlueprintRegistry()
        for name in ("a", "b", "c"):
            reg.register(_make_blueprint(name))
        names = {bp.name for bp in reg.list_blueprints()}
        assert names == {"a", "b", "c"}

    def test_registry_repr(self) -> None:
        reg = BlueprintRegistry()
        reg.register(_make_blueprint("alpha"))
        reg.register(_make_blueprint("beta"))
        r = repr(reg)
        assert "alpha" in r
        assert "beta" in r


# ---------------------------------------------------------------------------
# Orchestrator: route() tests
# ---------------------------------------------------------------------------


class TestOrchestratorRoute:
    def test_route_returns_highest_scored_blueprint(self) -> None:
        policy = _make_policy()
        bp_low = _make_blueprint("low-score")
        bp_high = _make_blueprint("high-score")
        orch = Orchestrator(
            policy,
            score_fn=_fixed_score({"low-score": 0.2, "high-score": 0.9}),
        )
        best, score = orch.route("some task", [bp_low, bp_high])
        assert best.name == "high-score"
        assert score == pytest.approx(0.9)

    def test_route_with_tie_returns_valid_blueprint(self) -> None:
        policy = _make_policy()
        bp_a = _make_blueprint("agent-a")
        bp_b = _make_blueprint("agent-b")
        orch = Orchestrator(
            policy,
            score_fn=_fixed_score({"agent-a": 0.5, "agent-b": 0.5}),
        )
        best, score = orch.route("task", [bp_a, bp_b])
        assert best in (bp_a, bp_b)
        assert score == pytest.approx(0.5)

    def test_route_empty_blueprints_raises_value_error(self) -> None:
        policy = _make_policy()
        orch = Orchestrator(policy, score_fn=_fixed_score({}))
        with pytest.raises(ValueError, match="empty"):
            orch.route("task", [])

    def test_route_score_clamped_above_one(self) -> None:
        policy = _make_policy()
        bp = _make_blueprint("over")

        def _over_score(task: str, blueprint: Blueprint, model_id: str) -> float:
            return 999.0

        orch = Orchestrator(policy, score_fn=_over_score)
        _, score = orch.route("task", [bp])
        assert score <= 1.0

    def test_route_score_clamped_below_zero(self) -> None:
        policy = _make_policy()
        bp = _make_blueprint("under")

        def _under_score(task: str, blueprint: Blueprint, model_id: str) -> float:
            return -5.0

        orch = Orchestrator(policy, score_fn=_under_score)
        _, score = orch.route("task", [bp])
        assert score >= 0.0

    def test_route_uses_routing_model_id(self) -> None:
        """Score function must receive the model_id of routing_model()."""
        policy = _make_policy()
        routing_entry = policy.routing_model()

        received_model_ids: list[str] = []

        def _capturing_score(
            task: str, blueprint: Blueprint, model_id: str
        ) -> float:
            received_model_ids.append(model_id)
            return 0.5

        bp = _make_blueprint("test-bp")
        orch = Orchestrator(policy, score_fn=_capturing_score)
        orch.route("a task", [bp])
        assert all(mid == routing_entry.model_id for mid in received_model_ids)

    def test_route_single_blueprint_returned_regardless_of_score(self) -> None:
        policy = _make_policy()
        bp = _make_blueprint("only")
        orch = Orchestrator(
            policy,
            score_fn=_fixed_score({"only": 0.0}),
        )
        best, score = orch.route("task", [bp])
        assert best.name == "only"
        assert score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Orchestrator: decompose() tests
# ---------------------------------------------------------------------------


class TestOrchestratorDecompose:
    def test_decompose_returns_list_from_decompose_fn(self) -> None:
        policy = _make_policy()
        subtasks = ["subtask A", "subtask B", "subtask C"]
        orch = Orchestrator(
            policy,
            score_fn=_fixed_score({}),
            decompose_fn=_fixed_decompose(subtasks),
        )
        result = orch.decompose("complex task")
        assert result == subtasks

    def test_decompose_passes_routing_model_id(self) -> None:
        policy = _make_policy()
        routing_entry = policy.routing_model()
        received: list[str] = []

        def _capturing_decompose(task: str, model_id: str) -> list[str]:
            received.append(model_id)
            return ["sub"]

        orch = Orchestrator(
            policy,
            score_fn=_fixed_score({}),
            decompose_fn=_capturing_decompose,
        )
        orch.decompose("task")
        assert received == [routing_entry.model_id]

    def test_decompose_empty_list_on_simple_task(self) -> None:
        policy = _make_policy()
        orch = Orchestrator(
            policy,
            score_fn=_fixed_score({}),
            decompose_fn=_fixed_decompose([]),
        )
        result = orch.decompose("trivial")
        assert result == []


# ---------------------------------------------------------------------------
# Orchestrator: assign() tests
# ---------------------------------------------------------------------------


class TestOrchestratorAssign:
    def test_assign_returns_assignment_instance(self) -> None:
        policy = _make_policy()
        bp = _make_blueprint("coding", tier=ModelTier.CAPABLE)
        orch = Orchestrator(policy, score_fn=_fixed_score({}))
        assignment = orch.assign(bp)
        assert isinstance(assignment, Assignment)

    def test_assign_uses_blueprint_tier(self) -> None:
        policy = _make_policy()
        bp = _make_blueprint("best-agent", tier=ModelTier.BEST)
        orch = Orchestrator(policy, score_fn=_fixed_score({}))
        assignment = orch.assign(bp)
        # The assigned model must be at least BEST tier
        assert assignment.tier >= ModelTier.BEST

    def test_assign_attaches_required_capabilities(self) -> None:
        policy = _make_policy(with_mcp=True)
        bp = _make_blueprint("searcher", capabilities=frozenset({"search"}))
        orch = Orchestrator(policy, score_fn=_fixed_score({}))
        assignment = orch.assign(bp)
        server_caps = {cap for s in assignment.mcp_servers for cap in s.capabilities}
        assert "search" in server_caps

    def test_assign_no_capabilities_gives_empty_mcp(self) -> None:
        policy = _make_policy()
        bp = _make_blueprint("plain")
        orch = Orchestrator(policy, score_fn=_fixed_score({}))
        assignment = orch.assign(bp)
        assert assignment.mcp_servers == ()


# ---------------------------------------------------------------------------
# Orchestrator: repr
# ---------------------------------------------------------------------------


class TestOrchestratorRepr:
    def test_repr_contains_policy(self) -> None:
        policy = _make_policy()
        orch = Orchestrator(policy, score_fn=_fixed_score({}))
        r = repr(orch)
        assert "Orchestrator" in r
        assert "policy" in r
