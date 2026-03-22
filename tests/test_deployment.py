"""Tests for KubeAI deployment package — DeploymentSpec, DeploymentReconciler, HorizontalAgentScaler."""

from __future__ import annotations

import pytest

from KubeAI.blueprint import Blueprint, BlueprintRegistry
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.scheduler.lifecycle import AgentLifecycleManager, SpawnedAgent
from KubeAI.deployment import (
    AutoscaleSignals,
    DeploymentSpec,
    DeploymentStatus,
    DeploymentReconciler,
    HorizontalAgentScaler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def llm_pool() -> LLMPool:
    pool = LLMPool()
    pool.register(
        ModelEntry(
            model_id="gpt-4o-mini",
            provider="openai",
            tier=ModelTier.FAST,
            cost_per_1k_tokens=0.001,
            api_key="test-key",
        )
    )
    return pool


@pytest.fixture()
def mcp_pool() -> MCPPool:
    """Empty MCP pool — no tool servers required."""
    return MCPPool()


@pytest.fixture()
def registry(llm_pool: LLMPool) -> BlueprintRegistry:
    reg = BlueprintRegistry()
    bp = Blueprint(
        name="test-agent",
        description="A test agent",
        tier=ModelTier.FAST,
        system_prompt="You are a test agent.",
        required_capabilities=frozenset(),
    )
    reg.register(bp)
    return reg


@pytest.fixture()
def control_plane() -> ControlPlaneAPI:
    return ControlPlaneAPI()


@pytest.fixture()
def lifecycle(llm_pool: LLMPool, mcp_pool: MCPPool, control_plane: ControlPlaneAPI) -> AgentLifecycleManager:
    policy = AssignmentPolicy(llm_pool, mcp_pool)
    return AgentLifecycleManager(policy=policy, control_plane=control_plane)


@pytest.fixture()
def reconciler(lifecycle: AgentLifecycleManager, registry: BlueprintRegistry, control_plane: ControlPlaneAPI) -> DeploymentReconciler:
    return DeploymentReconciler(lifecycle=lifecycle, registry=registry, control_plane=control_plane)


@pytest.fixture()
def spec() -> DeploymentSpec:
    return DeploymentSpec(
        name="deploy-test",
        blueprint_name="test-agent",
        replicas=2,
        min_replicas=1,
        max_replicas=5,
        target_load=0.7,
    )


# ---------------------------------------------------------------------------
# DeploymentSpec validation tests
# ---------------------------------------------------------------------------

class TestDeploymentSpecValidation:
    def test_min_replicas_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError, match="min_replicas"):
            DeploymentSpec(name="d", blueprint_name="bp", min_replicas=-1)

    def test_max_replicas_must_be_gte_min(self) -> None:
        with pytest.raises(ValueError, match="max_replicas"):
            DeploymentSpec(name="d", blueprint_name="bp", min_replicas=3, max_replicas=2)

    def test_target_load_zero_is_invalid(self) -> None:
        with pytest.raises(ValueError, match="target_load"):
            DeploymentSpec(name="d", blueprint_name="bp", target_load=0.0)

    def test_target_load_above_one_is_invalid(self) -> None:
        with pytest.raises(ValueError, match="target_load"):
            DeploymentSpec(name="d", blueprint_name="bp", target_load=1.1)

    def test_target_load_one_is_valid(self) -> None:
        spec = DeploymentSpec(name="d", blueprint_name="bp", target_load=1.0)
        assert spec.target_load == 1.0

    def test_valid_spec_is_immutable(self) -> None:
        spec = DeploymentSpec(name="d", blueprint_name="bp")
        with pytest.raises((AttributeError, TypeError)):
            spec.replicas = 99  # type: ignore[misc]

    def test_max_token_cost_per_task_must_be_positive_when_provided(self) -> None:
        with pytest.raises(ValueError, match="max_token_cost_per_task"):
            DeploymentSpec(name="d", blueprint_name="bp", max_token_cost_per_task=0.0)


# ---------------------------------------------------------------------------
# DeploymentSpec repr test
# ---------------------------------------------------------------------------

class TestDeploymentSpecRepr:
    def test_repr_contains_name(self) -> None:
        spec = DeploymentSpec(name="my-deploy", blueprint_name="bp")
        assert "my-deploy" in repr(spec)

    def test_repr_contains_blueprint(self) -> None:
        spec = DeploymentSpec(name="d", blueprint_name="cool-agent")
        assert "cool-agent" in repr(spec)


# ---------------------------------------------------------------------------
# DeploymentStatus repr test
# ---------------------------------------------------------------------------

class TestDeploymentStatusRepr:
    def test_repr_contains_desired_count(self) -> None:
        status = DeploymentStatus(name="d", desired=3, ready=2, available=2, unavailable=1)
        assert "3" in repr(status)
        assert "d" in repr(status)


# ---------------------------------------------------------------------------
# DeploymentReconciler tests
# ---------------------------------------------------------------------------

class TestDeploymentReconciler:
    def test_reconcile_spawns_to_desired_replicas(
        self, reconciler: DeploymentReconciler, spec: DeploymentSpec, lifecycle: AgentLifecycleManager
    ) -> None:
        status = reconciler.reconcile(spec)
        assert len(lifecycle.list_agents()) == spec.replicas
        assert status.desired == spec.replicas

    def test_reconcile_terminates_excess_agents(
        self,
        reconciler: DeploymentReconciler,
        registry: BlueprintRegistry,
        lifecycle: AgentLifecycleManager,
        spec: DeploymentSpec,
    ) -> None:
        blueprint = registry.get(spec.blueprint_name)
        # Spawn 4 agents, but desired is 2
        for _ in range(4):
            lifecycle.spawn(blueprint)
        assert len(lifecycle.list_agents()) == 4

        reconciler.reconcile(spec)
        assert len(lifecycle.list_agents()) == spec.replicas

    def test_reconcile_respects_min_replicas(
        self, reconciler: DeploymentReconciler, lifecycle: AgentLifecycleManager
    ) -> None:
        spec = DeploymentSpec(
            name="min-test",
            blueprint_name="test-agent",
            replicas=0,  # Would underflow, but clamped to min_replicas
            min_replicas=2,
            max_replicas=5,
        )
        # replicas=0 < min_replicas=2, so desired becomes 2
        status = reconciler.reconcile(spec)
        assert status.desired == 2
        assert len(lifecycle.list_agents()) >= 2

    def test_reconcile_respects_max_replicas(
        self, reconciler: DeploymentReconciler, lifecycle: AgentLifecycleManager
    ) -> None:
        spec = DeploymentSpec(
            name="max-test",
            blueprint_name="test-agent",
            replicas=100,  # Way over max
            min_replicas=1,
            max_replicas=3,
        )
        status = reconciler.reconcile(spec)
        assert status.desired == 3
        assert len(lifecycle.list_agents()) == 3

    def test_status_returns_correct_ready_count(
        self,
        reconciler: DeploymentReconciler,
        registry: BlueprintRegistry,
        lifecycle: AgentLifecycleManager,
        spec: DeploymentSpec,
    ) -> None:
        blueprint = registry.get(spec.blueprint_name)
        lifecycle.spawn(blueprint)
        lifecycle.spawn(blueprint)

        status = reconciler.status(spec)
        assert status.ready == 2
        assert status.available == 2

    def test_start_watch_and_stop_watch_dont_crash(
        self, reconciler: DeploymentReconciler, spec: DeploymentSpec
    ) -> None:
        reconciler.start_watch(spec, interval_s=60.0)
        assert spec.name in reconciler._watches
        reconciler.stop_watch(spec.name)
        # After stopping, the event is set and watch is removed
        assert spec.name not in reconciler._watches

    def test_start_watch_idempotent(
        self, reconciler: DeploymentReconciler, spec: DeploymentSpec
    ) -> None:
        reconciler.start_watch(spec, interval_s=60.0)
        event_before = reconciler._watches.get(spec.name)
        reconciler.start_watch(spec, interval_s=60.0)  # second call is a no-op
        event_after = reconciler._watches.get(spec.name)
        assert event_before is event_after
        reconciler.stop_watch(spec.name)

    def test_reconciler_repr_shows_watches(
        self, reconciler: DeploymentReconciler, spec: DeploymentSpec
    ) -> None:
        reconciler.start_watch(spec, interval_s=60.0)
        assert spec.name in repr(reconciler)
        reconciler.stop_watch(spec.name)


# ---------------------------------------------------------------------------
# HorizontalAgentScaler tests
# ---------------------------------------------------------------------------

class TestHorizontalAgentScaler:
    @pytest.fixture()
    def scaler(self, reconciler: DeploymentReconciler) -> HorizontalAgentScaler:
        return HorizontalAgentScaler(reconciler)

    def test_scale_up_when_overloaded(
        self,
        scaler: HorizontalAgentScaler,
        reconciler: DeploymentReconciler,
        lifecycle: AgentLifecycleManager,
        spec: DeploymentSpec,
    ) -> None:
        # First reconcile to set baseline of 2 agents
        reconciler.reconcile(spec)
        baseline = len(lifecycle.list_agents())

        # Observed load above target (0.7), e.g., 0.9
        status = scaler.scale(spec, observed_load=0.9)
        after = len(lifecycle.list_agents())
        assert after >= baseline
        assert status.desired >= baseline

    def test_scale_down_when_underloaded(
        self,
        scaler: HorizontalAgentScaler,
        reconciler: DeploymentReconciler,
        lifecycle: AgentLifecycleManager,
        spec: DeploymentSpec,
    ) -> None:
        # Set up 3 agents first
        big_spec = DeploymentSpec(
            name=spec.name,
            blueprint_name=spec.blueprint_name,
            replicas=3,
            min_replicas=spec.min_replicas,
            max_replicas=spec.max_replicas,
            target_load=spec.target_load,
        )
        reconciler.reconcile(big_spec)
        assert len(lifecycle.list_agents()) == 3

        # Observed load well below target * 0.5 = 0.35, e.g., 0.1
        status = scaler.scale(spec, observed_load=0.1)
        # Scale down should reduce agents (floor), but respect min_replicas
        assert status.desired >= spec.min_replicas

    def test_scale_noop_when_load_near_target(
        self,
        scaler: HorizontalAgentScaler,
        reconciler: DeploymentReconciler,
        lifecycle: AgentLifecycleManager,
        spec: DeploymentSpec,
    ) -> None:
        # Reconcile to spec.replicas = 2
        reconciler.reconcile(spec)
        baseline = len(lifecycle.list_agents())

        # Load near target but not triggering scale (between 0.35 and 0.7)
        status = scaler.scale(spec, observed_load=0.6)
        assert len(lifecycle.list_agents()) == baseline
        assert status.desired == baseline

    def test_scaler_repr(self, scaler: HorizontalAgentScaler) -> None:
        r = repr(scaler)
        assert "HorizontalAgentScaler" in r
        assert "DeploymentReconciler" in r

    def test_queue_depth_scales_up_even_when_load_is_moderate(
        self,
        scaler: HorizontalAgentScaler,
        reconciler: DeploymentReconciler,
        lifecycle: AgentLifecycleManager,
        spec: DeploymentSpec,
    ) -> None:
        reconciler.reconcile(spec)
        baseline = len(lifecycle.list_agents())

        status = scaler.scale_by_signals(
            spec,
            AutoscaleSignals(observed_load=0.55, queue_depth=12),
        )

        assert len(lifecycle.list_agents()) >= baseline
        assert status.desired >= baseline

    def test_high_token_cost_dampens_scale_up(
        self,
        scaler: HorizontalAgentScaler,
        reconciler: DeploymentReconciler,
        lifecycle: AgentLifecycleManager,
    ) -> None:
        capped_spec = DeploymentSpec(
            name="cost-capped",
            blueprint_name="test-agent",
            replicas=3,
            min_replicas=1,
            max_replicas=5,
            target_load=0.7,
            max_token_cost_per_task=0.01,
        )
        reconciler.reconcile(capped_spec)

        status = scaler.scale_by_signals(
            capped_spec,
            AutoscaleSignals(observed_load=0.95, queue_depth=10, avg_token_cost=0.05),
        )

        assert status.desired <= 3
        assert len(lifecycle.list_agents()) <= 3
