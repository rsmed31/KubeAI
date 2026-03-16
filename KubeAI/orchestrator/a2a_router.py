"""A2A router is the service-mesh analogue that routes agent-to-agent tasks through pooled capability-aware endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any, Iterable

from .a2a_pool import A2AAgentCard, A2AConnection, A2APool


@dataclass(frozen=True)
class RoutedA2ATask:
    """Immutable A2A dispatch envelope produced by A2ARouter."""

    task_id: str
    task: str
    target: A2AAgentCard
    connection: A2AConnection
    required_capabilities: tuple[str, ...] = field(default_factory=tuple)
    payload: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"RoutedA2ATask(task_id={self.task_id!r}, target={self.target.agent_id!r}, "
            f"connection={self.connection.connection_id!r}, capabilities={self.required_capabilities!r})"
        )


class A2ARouter:
    """Capability-aware task router that leases reusable A2A connections."""

    def __init__(self, pool: A2APool) -> None:
        self._pool = pool
        self._counter = count(1)

    def route(
        self,
        task: str,
        *,
        required_capabilities: Iterable[str] = (),
        preferred_agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RoutedA2ATask:
        """Route one task to a selected A2A endpoint and return dispatch metadata."""
        if not task.strip():
            raise ValueError("task must not be empty")

        target = self._pool.select(
            required_capabilities=required_capabilities,
            preferred_agent_id=preferred_agent_id,
            task=task,
        )
        connection = self._pool.acquire_connection(target.agent_id)
        task_id = f"a2a-task-{next(self._counter)}"

        return RoutedA2ATask(
            task_id=task_id,
            task=task,
            target=target,
            connection=connection,
            required_capabilities=tuple(sorted(set(required_capabilities))),
            payload=dict(payload or {}),
        )

    def complete(self, routed_task: RoutedA2ATask) -> None:
        """Release one pooled connection lease when dispatch completes."""
        self._pool.release_connection(routed_task.target.agent_id)

    def __repr__(self) -> str:
        return f"A2ARouter(pool={self._pool!r})"
