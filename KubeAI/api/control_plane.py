"""Control-plane API is the Kubernetes apiserver analogue that serves agent, task, event, and metrics state for CLI and UI clients."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from KubeAI.monitoring import EventStreamHub, MetricsStore

if TYPE_CHECKING:
    from KubeAI.orchestrator.a2a_pool import A2AAgentCard


@dataclass(frozen=True)
class AgentRecord:
    """Stable agent view model for API/UI consumption."""

    agent_id: str
    name: str
    description: str
    state: str
    healthy: bool
    load: float
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskRecord:
    """Task completion record used for task feed and monitoring pages."""

    task_id: str
    blueprint: str
    status: str
    latency_ms: float
    token_cost: float
    eval_score: float | None
    agent_id: str | None = None
    timestamp: float = 0.0


class ControlPlaneAPI:
    """In-memory control-plane facade for status, events, and metrics."""

    def __init__(
        self,
        metrics: MetricsStore | None = None,
        events: EventStreamHub | None = None,
    ) -> None:
        self._metrics = metrics or MetricsStore()
        self._events = events or EventStreamHub()
        self._agents: dict[str, AgentRecord] = {}
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.RLock()

    def register_agent(self, card: "A2AAgentCard", *, state: str = "running") -> AgentRecord:
        """Register or update an agent record from an A2A card."""
        normalized_state = state.strip() or "running"
        blueprint = self._infer_blueprint_name(card)

        record = AgentRecord(
            agent_id=card.agent_id,
            name=card.name,
            description=card.description,
            state=normalized_state,
            healthy=card.healthy,
            load=float(card.load),
            capabilities=tuple(sorted(card.capabilities)),
            metadata=dict(card.metadata),
        )

        with self._lock:
            self._agents[card.agent_id] = record

        self._metrics.inc_counter(
            "KubeAI_agent_spawns_total",
            labels={"blueprint": blueprint},
        )
        self._refresh_agent_pool_size(blueprint=blueprint)
        self._events.publish(
            "agent.registered",
            {
                "agent_id": record.agent_id,
                "blueprint": blueprint,
                "state": record.state,
            },
        )
        return record

    def update_agent_state(
        self,
        agent_id: str,
        *,
        state: str | None = None,
        healthy: bool | None = None,
        load: float | None = None,
    ) -> AgentRecord:
        """Update an existing agent state for dashboard/status views."""
        with self._lock:
            current = self._agents.get(agent_id)
            if current is None:
                raise KeyError(f"Agent {agent_id!r} not registered")

            updated = AgentRecord(
                agent_id=current.agent_id,
                name=current.name,
                description=current.description,
                state=(state if state is not None else current.state),
                healthy=(healthy if healthy is not None else current.healthy),
                load=(float(load) if load is not None else current.load),
                capabilities=current.capabilities,
                metadata=dict(current.metadata),
            )
            self._agents[agent_id] = updated

        blueprint = self._infer_blueprint_name_from_record(updated)
        self._refresh_agent_pool_size(blueprint=blueprint)
        self._events.publish(
            "agent.state_updated",
            {
                "agent_id": updated.agent_id,
                "state": updated.state,
                "healthy": updated.healthy,
                "load": updated.load,
            },
        )
        return updated

    def list_agents(self) -> list[AgentRecord]:
        """Return all tracked agent records in deterministic order."""
        with self._lock:
            return [self._agents[key] for key in sorted(self._agents)]

    def get_agent(self, agent_id: str) -> AgentRecord:
        """Return one agent record by id."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                raise KeyError(f"Agent {agent_id!r} not registered")
            return agent

    def record_task_result(
        self,
        *,
        task_id: str,
        blueprint: str,
        status: str,
        latency_ms: float,
        token_cost: float,
        eval_score: float | None = None,
        agent_id: str | None = None,
    ) -> TaskRecord:
        """Record task completion and update monitoring metrics/events."""
        normalized_status = status.strip() or "unknown"
        timestamp = time.time()
        record = TaskRecord(
            task_id=task_id,
            blueprint=blueprint,
            status=normalized_status,
            latency_ms=float(latency_ms),
            token_cost=float(token_cost),
            eval_score=(float(eval_score) if eval_score is not None else None),
            agent_id=agent_id,
            timestamp=timestamp,
        )

        with self._lock:
            self._tasks[task_id] = record

        self._metrics.inc_counter(
            "KubeAI_tasks_total",
            labels={"blueprint": blueprint, "status": normalized_status},
        )
        self._metrics.observe_histogram(
            "KubeAI_task_latency_ms",
            value=record.latency_ms,
            labels={"blueprint": blueprint},
        )
        self._metrics.inc_counter(
            "KubeAI_token_cost_total",
            value=record.token_cost,
            labels={"blueprint": blueprint, "provider": "unknown"},
        )
        if record.eval_score is not None:
            self._metrics.observe_histogram(
                "KubeAI_eval_score",
                value=record.eval_score,
                labels={"blueprint": blueprint},
            )

        self._events.publish(
            "task.recorded",
            {
                "task_id": record.task_id,
                "blueprint": record.blueprint,
                "status": record.status,
                "agent_id": record.agent_id,
                "latency_ms": record.latency_ms,
            },
        )
        return record

    def list_tasks(self, *, limit: int = 100) -> list[TaskRecord]:
        """Return most recent task records ordered by timestamp ascending."""
        max_items = max(1, limit)
        with self._lock:
            ordered = sorted(self._tasks.values(), key=lambda task: task.timestamp)
        return ordered[-max_items:]

    def list_events(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        after_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return event stream records as JSON-friendly dictionaries."""
        events = self._events.list_events(
            limit=limit,
            event_type=event_type,
            after_event_id=after_event_id,
        )
        return [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "timestamp": event.timestamp,
                "payload": dict(event.payload),
            }
            for event in events
        ]

    def get_overview(self) -> dict[str, Any]:
        """Return Kubernetes-dashboard-style overview card data."""
        with self._lock:
            agents = list(self._agents.values())
            tasks = list(self._tasks.values())

        active_agents = sum(1 for agent in agents if agent.state in {"running", "idle"})
        avg_latency = (
            float(sum(task.latency_ms for task in tasks) / len(tasks))
            if tasks
            else 0.0
        )
        avg_eval = (
            float(
                sum(task.eval_score for task in tasks if task.eval_score is not None)
                / max(1, sum(1 for task in tasks if task.eval_score is not None))
            )
            if any(task.eval_score is not None for task in tasks)
            else 0.0
        )

        return {
            "agents_total": len(agents),
            "active_agents": active_agents,
            "tasks_total": len(tasks),
            "avg_latency_ms": avg_latency,
            "avg_eval_score": avg_eval,
            "latest_event_id": self._events.latest_event_id(),
        }

    def metrics_snapshot(self) -> dict[str, list[dict[str, object]]]:
        """Return full metrics snapshot."""
        return self._metrics.snapshot()

    def metrics_text(self) -> str:
        """Return Prometheus-style metrics text."""
        return self._metrics.render_prometheus_text()

    @staticmethod
    def _infer_blueprint_name(card: "A2AAgentCard") -> str:
        metadata_blueprint = card.metadata.get("blueprint") if isinstance(card.metadata, dict) else None
        if isinstance(metadata_blueprint, str) and metadata_blueprint.strip():
            return metadata_blueprint.strip()

        name = card.name.strip()
        if "-" not in name:
            return name or "unknown"
        return name.split("-", 1)[0]

    @staticmethod
    def _infer_blueprint_name_from_record(record: AgentRecord) -> str:
        metadata_blueprint = record.metadata.get("blueprint") if isinstance(record.metadata, dict) else None
        if isinstance(metadata_blueprint, str) and metadata_blueprint.strip():
            return metadata_blueprint.strip()

        name = record.name.strip()
        if "-" not in name:
            return name or "unknown"
        return name.split("-", 1)[0]

    def _refresh_agent_pool_size(self, *, blueprint: str) -> None:
        with self._lock:
            running = sum(
                1
                for record in self._agents.values()
                if self._infer_blueprint_name_from_record(record) == blueprint
                and record.state in {"running", "idle"}
            )
            failed = sum(
                1
                for record in self._agents.values()
                if self._infer_blueprint_name_from_record(record) == blueprint
                and not record.healthy
            )

        self._metrics.set_gauge(
            "KubeAI_agent_pool_size",
            value=float(running),
            labels={"blueprint": blueprint, "state": "running"},
        )
        self._metrics.set_gauge(
            "KubeAI_agent_pool_size",
            value=float(failed),
            labels={"blueprint": blueprint, "state": "failed"},
        )

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"ControlPlaneAPI(agents={len(self._agents)}, "
                f"tasks={len(self._tasks)}, metrics={self._metrics!r}, "
                f"events={self._events!r})"
            )
