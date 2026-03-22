"""Tests for AutoscaleController, the HPA-style background controller that continuously scales from control-plane signals."""

from __future__ import annotations

import time

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.blueprint import Blueprint, BlueprintRegistry
from KubeAI.deployment import (
    AutoscaleController,
    AutoscaleControllerConfig,
    DeploymentReconciler,
    DeploymentSpec,
    HorizontalAgentScaler,
)
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool
from KubeAI.scheduler.lifecycle import AgentLifecycleManager


def _build_runtime_components() -> tuple[
    ControlPlaneAPI,
    BlueprintRegistry,
    AgentLifecycleManager,
    DeploymentReconciler,
    HorizontalAgentScaler,
]:
    llm_pool = LLMPool()
    llm_pool.register(
        ModelEntry(
            model_id="gpt-4o-mini",
            provider="openai",
            tier=ModelTier.FAST,
            cost_per_1k_tokens=0.001,
        )
    )

    mcp_pool = MCPPool()
    policy = AssignmentPolicy(llm_pool, mcp_pool)

    control_plane = ControlPlaneAPI()
    lifecycle = AgentLifecycleManager(policy=policy, control_plane=control_plane)

    registry = BlueprintRegistry()
    registry.register(
        Blueprint(
            name="test-agent",
            description="Autoscale test agent",
            tier=ModelTier.FAST,
            system_prompt="You are a test agent.",
            required_capabilities=frozenset(),
        )
    )

    reconciler = DeploymentReconciler(lifecycle=lifecycle, registry=registry, control_plane=control_plane)
    scaler = HorizontalAgentScaler(reconciler)

    return control_plane, registry, lifecycle, reconciler, scaler


def test_run_once_scales_from_live_queue_signals() -> None:
    control_plane, _registry, lifecycle, reconciler, scaler = _build_runtime_components()
    spec = DeploymentSpec(
        name="deploy-test-agent",
        blueprint_name="test-agent",
        replicas=1,
        min_replicas=1,
        max_replicas=4,
        target_load=0.7,
    )
    controller = AutoscaleController(control_plane, reconciler, scaler, specs=[spec])

    control_plane.submit_task("Summarize this doc", blueprint="test-agent")
    statuses = controller.run_once()

    assert "deploy-test-agent" in statuses
    assert statuses["deploy-test-agent"].desired >= 1
    assert len(lifecycle.list_agents()) >= 1


def test_run_once_skips_cold_start_when_no_signal() -> None:
    control_plane, _registry, lifecycle, reconciler, scaler = _build_runtime_components()
    spec = DeploymentSpec(
        name="deploy-test-agent",
        blueprint_name="test-agent",
        replicas=1,
        min_replicas=1,
        max_replicas=4,
        target_load=0.7,
    )
    controller = AutoscaleController(control_plane, reconciler, scaler, specs=[spec])

    statuses = controller.run_once()

    assert statuses["deploy-test-agent"].ready == 0
    assert len(lifecycle.list_agents()) == 0


def test_background_loop_scales_continuously() -> None:
    control_plane, _registry, lifecycle, reconciler, scaler = _build_runtime_components()
    spec = DeploymentSpec(
        name="deploy-test-agent",
        blueprint_name="test-agent",
        replicas=1,
        min_replicas=1,
        max_replicas=4,
        target_load=0.7,
    )
    controller = AutoscaleController(
        control_plane,
        reconciler,
        scaler,
        specs=[spec],
        config=AutoscaleControllerConfig(interval_s=0.05),
    )

    controller.start()
    try:
        control_plane.submit_task("Run continuous autoscale", blueprint="test-agent")
        time.sleep(0.2)
    finally:
        controller.stop()

    assert len(lifecycle.list_agents()) >= 1
