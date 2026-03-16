"""A2A pool is the service-endpoint cache analogue that tracks agent cards and reuses routes by capability."""

from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable


_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


@dataclass
class A2AAgentCard:
    """Capability advertisement for one running agent endpoint."""

    agent_id: str
    name: str
    endpoint: str
    capabilities: frozenset[str]
    description: str = ""
    load: float = 0.0
    healthy: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"A2AAgentCard(agent_id={self.agent_id!r}, "
            f"capabilities={sorted(self.capabilities)!r}, "
            f"load={self.load:.2f}, healthy={self.healthy})"
        )


@dataclass
class A2AConnection:
    """Reusable connection handle for one target agent endpoint."""

    connection_id: str
    agent_id: str
    endpoint: str
    reuse_count: int = 0

    def __repr__(self) -> str:
        return (
            f"A2AConnection(connection_id={self.connection_id!r}, "
            f"agent_id={self.agent_id!r}, reuse_count={self.reuse_count})"
        )


class A2APool:
    """Registry and selector for capability-aware agent-to-agent routing."""

    _LOAD_THRESHOLD: float = 0.9

    def __init__(self) -> None:
        self._agents: dict[str, A2AAgentCard] = {}
        self._connections: dict[str, A2AConnection] = {}
        self._connection_seq: int = 0
        self._lock = threading.RLock()

    def register(self, card: A2AAgentCard) -> None:
        """Add or replace an A2A agent card."""
        with self._lock:
            self._agents[card.agent_id] = copy.copy(card)
            self._agents[card.agent_id].metadata = dict(card.metadata)

    def unregister(self, agent_id: str) -> None:
        """Remove an agent card and any pooled connection for it."""
        with self._lock:
            if agent_id not in self._agents:
                raise KeyError(f"A2A agent {agent_id!r} not registered")
            del self._agents[agent_id]
            self._connections.pop(agent_id, None)

    def update_health(
        self,
        agent_id: str,
        *,
        healthy: bool,
        load: float | None = None,
    ) -> None:
        """Update health and optional load for a registered A2A agent."""
        with self._lock:
            card = self._agents.get(agent_id)
            if card is None:
                raise KeyError(f"A2A agent {agent_id!r} not registered")
            card.healthy = healthy
            if load is not None:
                card.load = load

    def select(
        self,
        required_capabilities: Iterable[str] = (),
        *,
        preferred_agent_id: str | None = None,
        task: str = "",
    ) -> A2AAgentCard:
        """Select the best matching A2A target from capability and load signals."""
        needed = set(required_capabilities)
        with self._lock:
            if not self._agents:
                raise RuntimeError("A2APool has no registered agents")

            matching = [
                card
                for card in self._agents.values()
                if needed.issubset(card.capabilities)
            ]
            if needed and not matching:
                raise ValueError(
                    f"No A2A agent satisfies capabilities: {sorted(needed)!r}"
                )
            if not matching:
                matching = list(self._agents.values())

            healthy = [card for card in matching if card.healthy]
            candidates = healthy or matching

            if preferred_agent_id is not None:
                preferred = [card for card in candidates if card.agent_id == preferred_agent_id]
                if preferred:
                    chosen = preferred[0]
                    if chosen.load <= self._LOAD_THRESHOLD or len(candidates) == 1:
                        return copy.copy(chosen)

            def _score(card: A2AAgentCard) -> tuple[int, int, float, float, str]:
                overlap = len(card.capabilities.intersection(needed))
                overload = int(card.load > self._LOAD_THRESHOLD)
                relevance = self._text_overlap(
                    task,
                    f"{card.name} {card.description}",
                )
                return (overload, -overlap, -relevance, card.load, card.agent_id)

            ranked = sorted(candidates, key=_score)
            return copy.copy(ranked[0])

    @staticmethod
    def _text_overlap(task: str, description: str) -> float:
        if not task.strip() or not description.strip():
            return 0.0

        task_tokens = set(_TOKEN_PATTERN.findall(task.lower()))
        desc_tokens = set(_TOKEN_PATTERN.findall(description.lower()))
        if not task_tokens or not desc_tokens:
            return 0.0

        return float(len(task_tokens.intersection(desc_tokens)))

    def acquire_connection(self, agent_id: str) -> A2AConnection:
        """Return a reusable connection handle for an agent endpoint."""
        with self._lock:
            card = self._agents.get(agent_id)
            if card is None:
                raise KeyError(f"A2A agent {agent_id!r} not registered")

            connection = self._connections.get(agent_id)
            if connection is None:
                self._connection_seq += 1
                connection = A2AConnection(
                    connection_id=f"a2a-conn-{self._connection_seq}",
                    agent_id=card.agent_id,
                    endpoint=card.endpoint,
                    reuse_count=0,
                )
                self._connections[agent_id] = connection

            connection.reuse_count += 1
            return copy.copy(connection)

    def release_connection(self, agent_id: str) -> None:
        """Release one connection lease from a previously routed A2A call."""
        with self._lock:
            connection = self._connections.get(agent_id)
            if connection is None:
                return
            connection.reuse_count = max(0, connection.reuse_count - 1)

    def list_agents(self) -> list[A2AAgentCard]:
        """Return a snapshot of registered A2A agent cards."""
        with self._lock:
            return [copy.copy(card) for card in self._agents.values()]

    def list_connections(self) -> list[A2AConnection]:
        """Return a snapshot of pooled A2A connections."""
        with self._lock:
            return [copy.copy(connection) for connection in self._connections.values()]

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"A2APool(agents={len(self._agents)}, "
                f"connections={len(self._connections)})"
            )
