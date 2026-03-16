"""AgentLifecycleManager is the ReplicaSet controller analogue: spawns, tracks, and terminates agent instances while keeping the ControlPlaneAPI in sync."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from KubeAI.api.control_plane import AgentRecord, ControlPlaneAPI
from KubeAI.memory.shared_memory import SharedMemory
from KubeAI.orchestrator.assignment import Assignment, AssignmentPolicy
from KubeAI.orchestrator.llm_pool import ModelTier

if TYPE_CHECKING:
    from KubeAI.blueprint import Blueprint


@dataclass
class SpawnedAgent:
    """Runtime handle for a spawned agent instance."""

    agent_id: str
    blueprint: Blueprint
    assignment: Assignment
    spawned_at: float = field(default_factory=time.time)
    state: str = "running"       # running | idle | terminated
    task_count: int = 0

    def __repr__(self) -> str:
        return (
            f"SpawnedAgent(agent_id={self.agent_id!r}, blueprint={self.blueprint.name!r}, "
            f"state={self.state!r}, tasks={self.task_count})"
        )


class AgentLifecycleManager:
    """
    Manages agent spawn/idle/terminate lifecycle and syncs state to ControlPlaneAPI.

    spawn(blueprint, cost_hint) -> SpawnedAgent
    mark_idle(agent_id) -> None
    terminate(agent_id) -> None
    list_agents() -> list[SpawnedAgent]
    get_or_spawn(blueprint, cost_hint) -> SpawnedAgent   # reuse idle or spawn new
    """

    def __init__(
        self,
        policy: AssignmentPolicy,
        control_plane: ControlPlaneAPI,
        memory: SharedMemory | None = None,
        max_idle_s: float = 300.0,
    ) -> None:
        self._policy = policy
        self._cp = control_plane
        self._memory = memory or SharedMemory()
        self._max_idle_s = max_idle_s
        self._agents: dict[str, SpawnedAgent] = {}
        self._lock = threading.RLock()
        self._start_gc_thread()

    def spawn(self, blueprint: Blueprint, cost_hint: float = 0.5) -> SpawnedAgent:
        """Spawn a new agent, assign model+MCPs, register in control plane."""
        assignment = self._policy.assign(
            blueprint_tier=blueprint.tier,
            required_capabilities=blueprint.required_capabilities,
            cost_hint=cost_hint,
        )
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        agent = SpawnedAgent(
            agent_id=agent_id,
            blueprint=blueprint,
            assignment=assignment,
        )
        with self._lock:
            self._agents[agent_id] = agent
        # Register in ControlPlaneAPI
        self._cp._agents[agent_id] = AgentRecord(
            agent_id=agent_id,
            name=f"{blueprint.name}-{agent_id[-4:]}",
            description=blueprint.description,
            state="running",
            healthy=True,
            load=0.0,
            capabilities=tuple(sorted(blueprint.required_capabilities)),
            metadata={
                "blueprint": blueprint.name,
                "model": assignment.model_id,
                "tier": assignment.tier.value,
                "mcp_servers": [s.server_id for s in assignment.mcp_servers],
            },
        )
        self._cp._events.publish("agent.spawned", {
            "agent_id": agent_id,
            "blueprint": blueprint.name,
            "model_id": assignment.model_id,
        })
        return agent

    def get_or_spawn(self, blueprint: Blueprint, cost_hint: float = 0.5) -> SpawnedAgent:
        """Return an idle agent for this blueprint, or spawn a new one."""
        with self._lock:
            for agent in self._agents.values():
                if agent.blueprint.name == blueprint.name and agent.state == "idle":
                    agent.state = "running"
                    self._cp.update_agent_state(agent.agent_id, state="running")
                    return agent
        return self.spawn(blueprint, cost_hint=cost_hint)

    def mark_idle(self, agent_id: str) -> None:
        """Mark an agent as idle after completing a task."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                return
            agent.state = "idle"
        try:
            self._cp.update_agent_state(agent_id, state="idle")
        except KeyError:
            pass

    def record_task_complete(self, agent_id: str) -> None:
        """Increment task counter for an agent."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent:
                agent.task_count += 1

    def terminate(self, agent_id: str) -> bool:
        """Terminate an agent, snapshot working memory, update control plane."""
        with self._lock:
            agent = self._agents.pop(agent_id, None)
        if agent is None:
            return False
        agent.state = "terminated"
        self._memory.clear_working(agent_id)
        self._cp.terminate_agent(agent_id)
        self._cp._events.publish("agent.terminated", {"agent_id": agent_id})
        return True

    def list_agents(self) -> list[SpawnedAgent]:
        """Return all currently tracked (non-terminated) agent instances."""
        with self._lock:
            return list(self._agents.values())

    def _start_gc_thread(self) -> None:
        def _gc() -> None:
            while True:
                time.sleep(30)
                now = time.time()
                with self._lock:
                    idle_expired = [
                        aid for aid, a in self._agents.items()
                        if a.state == "idle"
                        and (now - a.spawned_at) > self._max_idle_s
                    ]
                for aid in idle_expired:
                    self.terminate(aid)

        t = threading.Thread(target=_gc, daemon=True)
        t.start()

    def __repr__(self) -> str:
        with self._lock:
            running = sum(1 for a in self._agents.values() if a.state == "running")
            idle = sum(1 for a in self._agents.values() if a.state == "idle")
        return f"AgentLifecycleManager(running={running}, idle={idle})"
