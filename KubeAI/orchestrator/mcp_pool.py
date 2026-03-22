"""MCPPool is the service-mesh analogue: registers MCP servers by capability tag and resolves multi-MCP attachments per task."""

from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass
from typing import Iterable


_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


@dataclass
class MCPServer:
    """Registry entry for a single MCP (Model Context Protocol) server."""

    server_id: str
    endpoint: str
    capabilities: frozenset[str]
    healthy: bool = True
    description: str = ""
    transport: str = "http"
    timeout_s: float = 15.0
    tags: frozenset[str] = frozenset()
    auth_headers: dict[str, str] | None = None

    def __repr__(self) -> str:
        caps = ", ".join(sorted(self.capabilities))
        return (
            f"MCPServer(server_id={self.server_id!r}, "
            f"capabilities=[{caps}], transport={self.transport!r}, healthy={self.healthy})"
        )


class MCPPool:
    """
    Registry and matcher for MCP tool servers.

    Analogous to a Kubernetes service registry: maintains a catalog of
    capability-tagged MCP servers and resolves the minimal covering set
    of servers needed to satisfy a task's required capability set.

    An agent may receive multiple MCP servers at spawn — one per disjoint
    capability group when no single server covers all requirements.
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServer] = {}
        self._lock = threading.RLock()

    def register(self, server: MCPServer) -> None:
        """Add or replace an MCP server in the pool (stored as a defensive copy)."""
        with self._lock:
            self._servers[server.server_id] = copy.copy(server)

    def update_health(self, server_id: str, *, healthy: bool) -> None:
        """Mark an MCP server healthy or unhealthy."""
        with self._lock:
            entry = self._servers.get(server_id)
            if entry is None:
                raise KeyError(f"MCP server {server_id!r} not registered")
            entry.healthy = healthy

    def select(
        self,
        required_capabilities: Iterable[str],
        *,
        require_healthy: bool = True,
        task: str = "",
    ) -> list[MCPServer]:
        """
        Return the minimal list of MCP servers that collectively cover all
        required capabilities.

        Uses a greedy set-cover: at each step picks the server that covers
        the most uncovered capabilities. Healthy servers are preferred;
        unhealthy servers act as a fallback when no healthy server can
        satisfy a remaining capability.

        Args:
            required_capabilities: Capability tags the task needs.
            require_healthy: When True (default), prefer healthy servers and
                             only use unhealthy ones as a last resort.

        Returns:
            List of MCPServer instances whose union satisfies all requirements.

        Raises:
            ValueError: If any required capability cannot be satisfied by any
                        registered server (healthy or otherwise).
        """
        needed = set(required_capabilities)
        if not needed:
            return []

        with self._lock:
            healthy_pool = [s for s in self._servers.values() if s.healthy]
            full_pool = list(self._servers.values())

        primary = healthy_pool if require_healthy else full_pool
        return self._greedy_cover(needed, primary, full_pool, task=task)

    @staticmethod
    def _greedy_cover(
        needed: set[str],
        candidates: list[MCPServer],
        fallback_pool: list[MCPServer],
        *,
        task: str,
    ) -> list[MCPServer]:
        """Greedy set-cover returning the minimal server list for *needed*."""
        selected: list[MCPServer] = []
        remaining = set(needed)

        while remaining:
            # Pick best from primary candidates first
            best = max(
                (s for s in candidates if s not in selected),
                key=lambda s: (
                    len(s.capabilities & remaining),
                    MCPPool._text_overlap(task, f"{s.server_id} {s.description}"),
                    s.server_id,
                ),
                default=None,
            )
            if best is None or not (best.capabilities & remaining):
                # Primary exhausted — fall back to full pool (may include unhealthy)
                best = max(
                    (s for s in fallback_pool if s not in selected),
                    key=lambda s: (
                        len(s.capabilities & remaining),
                        MCPPool._text_overlap(task, f"{s.server_id} {s.description}"),
                        s.server_id,
                    ),
                    default=None,
                )
                if best is None or not (best.capabilities & remaining):
                    raise ValueError(
                        f"No MCP server can satisfy capabilities: {remaining!r}"
                    )
            selected.append(best)
            remaining -= best.capabilities

        return selected

    @staticmethod
    def _text_overlap(task: str, description: str) -> float:
        if not task.strip() or not description.strip():
            return 0.0

        task_tokens = set(_TOKEN_PATTERN.findall(task.lower()))
        desc_tokens = set(_TOKEN_PATTERN.findall(description.lower()))
        if not task_tokens or not desc_tokens:
            return 0.0

        return float(len(task_tokens.intersection(desc_tokens)))

    def list_servers(self) -> list[MCPServer]:
        """Return a snapshot of all registered MCP servers."""
        with self._lock:
            return list(self._servers.values())

    def __repr__(self) -> str:
        with self._lock:
            return f"MCPPool(servers={len(self._servers)})"
