"""Tests for AgentLifecycleManager (scheduler/lifecycle.py) — the ReplicaSet controller analogue."""

from __future__ import annotations

import pytest

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.blueprint import Blueprint
from KubeAI.memory.shared_memory import SharedMemory
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool
from KubeAI.scheduler.lifecycle import AgentLifecycleManager, SpawnedAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def policy() -> AssignmentPolicy:
    """Minimal AssignmentPolicy with one FAST model and empty MCPPool."""
    pool = LLMPool()
    pool.register(
        ModelEntry(
            model_id="test-model",
            provider="test",
            tier=ModelTier.FAST,
            cost_per_1k_tokens=0.001,
        )
    )
    return AssignmentPolicy(pool, MCPPool())


@pytest.fixture()
def control_plane() -> ControlPlaneAPI:
    return ControlPlaneAPI()


@pytest.fixture()
def memory() -> SharedMemory:
    return SharedMemory()


@pytest.fixture()
def manager(
    policy: AssignmentPolicy,
    control_plane: ControlPlaneAPI,
    memory: SharedMemory,
) -> AgentLifecycleManager:
    return AgentLifecycleManager(
        policy=policy,
        control_plane=control_plane,
        memory=memory,
        max_idle_s=300.0,
    )


@pytest.fixture()
def blueprint() -> Blueprint:
    # No required_capabilities so the empty MCPPool does not raise.
    return Blueprint(
        name="research",
        description="Researches topics thoroughly.",
        tier=ModelTier.FAST,
        required_capabilities=frozenset(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_spawn_creates_spawned_agent_with_correct_blueprint(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """spawn() must return a SpawnedAgent referencing the given Blueprint."""
    agent = manager.spawn(blueprint)
    assert isinstance(agent, SpawnedAgent)
    assert agent.blueprint.name == blueprint.name
    assert agent.state == "pending"
    assert agent.task_count == 0


def test_spawn_registers_agent_in_control_plane(
    manager: AgentLifecycleManager,
    control_plane: ControlPlaneAPI,
    blueprint: Blueprint,
) -> None:
    """spawn() must register an AgentRecord in ControlPlaneAPI."""
    agent = manager.spawn(blueprint)
    record = control_plane.get_agent(agent.agent_id)
    assert record.agent_id == agent.agent_id
    assert record.state == "pending"
    assert record.metadata["blueprint"] == blueprint.name


def test_spawn_emits_agent_spawned_event(
    manager: AgentLifecycleManager,
    control_plane: ControlPlaneAPI,
    blueprint: Blueprint,
) -> None:
    """spawn() must publish an 'agent.spawned' event to the event stream."""
    agent = manager.spawn(blueprint)
    events = control_plane.list_events(event_type="agent.spawned", limit=50)
    agent_ids = [e["payload"].get("agent_id") for e in events]
    assert agent.agent_id in agent_ids


def test_get_or_spawn_reuses_idle_agent(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """get_or_spawn() must return an existing idle agent rather than spawning a new one."""
    first = manager.spawn(blueprint)
    manager.mark_idle(first.agent_id)

    second = manager.get_or_spawn(blueprint)
    assert second.agent_id == first.agent_id
    assert second.state == "running"
    # Only one agent should exist in the pool
    assert len(manager.list_agents()) == 1


def test_get_or_spawn_spawns_new_when_no_idle_available(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """get_or_spawn() must spawn a fresh agent when all existing agents are running."""
    first = manager.spawn(blueprint)
    # first is still running, so get_or_spawn must create a second one
    second = manager.get_or_spawn(blueprint)
    assert second.agent_id != first.agent_id
    assert len(manager.list_agents()) == 2


def test_mark_idle_updates_agent_state(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """mark_idle() must transition the agent state from 'pending' to 'idle'."""
    agent = manager.spawn(blueprint)
    assert agent.state == "pending"
    manager.mark_idle(agent.agent_id)
    assert agent.state == "idle"


def test_mark_idle_updates_control_plane_state(
    manager: AgentLifecycleManager,
    control_plane: ControlPlaneAPI,
    blueprint: Blueprint,
) -> None:
    """mark_idle() must also update the agent state in ControlPlaneAPI."""
    agent = manager.spawn(blueprint)
    manager.mark_idle(agent.agent_id)
    record = control_plane.get_agent(agent.agent_id)
    assert record.state == "idle"


def test_record_task_complete_increments_counter(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """record_task_complete() must increment the agent's task_count by 1 each call."""
    agent = manager.spawn(blueprint)
    assert agent.task_count == 0
    manager.record_task_complete(agent.agent_id)
    assert agent.task_count == 1
    manager.record_task_complete(agent.agent_id)
    assert agent.task_count == 2


def test_terminate_removes_agent_from_list(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """terminate() must remove the agent from list_agents()."""
    agent = manager.spawn(blueprint)
    assert any(a.agent_id == agent.agent_id for a in manager.list_agents())
    manager.terminate(agent.agent_id)
    assert all(a.agent_id != agent.agent_id for a in manager.list_agents())


def test_terminate_clears_working_memory(
    manager: AgentLifecycleManager,
    memory: SharedMemory,
    blueprint: Blueprint,
) -> None:
    """terminate() must clear all working-tier memory entries for the agent."""
    agent = manager.spawn(blueprint)
    memory.set_working(agent.agent_id, "ctx", "some context data")
    assert memory.get_working(agent.agent_id, "ctx") == "some context data"
    manager.terminate(agent.agent_id)
    assert memory.get_working(agent.agent_id, "ctx") is None


def test_terminate_returns_false_for_unknown_agent(
    manager: AgentLifecycleManager,
) -> None:
    """terminate() must return False when the agent_id is not tracked."""
    result = manager.terminate("agent-does-not-exist")
    assert result is False


def test_list_agents_returns_all_non_terminated(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """list_agents() must include all spawned, non-terminated agents."""
    a1 = manager.spawn(blueprint)
    a2 = manager.spawn(blueprint)
    a3 = manager.spawn(blueprint)
    manager.terminate(a2.agent_id)

    live = manager.list_agents()
    live_ids = {a.agent_id for a in live}
    assert a1.agent_id in live_ids
    assert a3.agent_id in live_ids
    assert a2.agent_id not in live_ids


def test_repr_shows_running_and_idle_counts(
    manager: AgentLifecycleManager,
    blueprint: Blueprint,
) -> None:
    """AgentLifecycleManager.__repr__ must reflect current running/idle counts."""
    a1 = manager.spawn(blueprint)
    a2 = manager.spawn(blueprint)
    manager.record_task_complete(a2.agent_id)
    manager.mark_idle(a1.agent_id)
    r = repr(manager)
    assert "running=1" in r
    assert "idle=1" in r


def test_spawned_agent_repr(blueprint: Blueprint, policy: AssignmentPolicy) -> None:
    """SpawnedAgent.__repr__ must include agent_id, blueprint name, state, and task count."""
    assignment = policy.assign(blueprint_tier=blueprint.tier)
    agent = SpawnedAgent(agent_id="agent-abcd1234", blueprint=blueprint, assignment=assignment)
    r = repr(agent)
    assert "agent-abcd1234" in r
    assert "research" in r
    assert "pending" in r
    assert "tasks=0" in r
