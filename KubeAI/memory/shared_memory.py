"""SharedMemory is the namespace analogue: routes agent state across working, short-term, and long-term tiers by scoped key prefix."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .etcd_backend import EtcdBackend

from .base import SharedMemoryBackend
from .in_memory import InMemoryBackend
from .sqlite_backend import SQLiteBackend


class SharedMemory:
    """Three-tier agent state store.

    Tier layout (mirrors Kubernetes volume types):
      working    — ephemeral per-agent context  (InMemoryBackend, no TTL)
      short_term — session-scoped shared state  (InMemoryBackend, TTL-bounded)
            long_term  — blueprint-scoped persistence (SQLiteBackend or EtcdBackend)

    Key namespacing:
      working    → "working:{agent_id}:{key}"
      short_term → "short_term:{domain}:{key}"
      long_term  → "long_term:{blueprint}:{key}"
    """

    def __init__(
        self,
        working: SharedMemoryBackend | None = None,
        short_term: SharedMemoryBackend | None = None,
        long_term: SharedMemoryBackend | None = None,
        short_term_ttl_s: float = 600.0,
        db_path: str = str(Path.home() / ".kubeai" / "memory.db"),
        long_term_backend: str = "sqlite",
        etcd_host: str = "127.0.0.1",
        etcd_port: int = 2379,
        etcd_namespace: str = "kubeai",
        etcd_timeout_s: float = 5.0,
        etcd_user: str | None = None,
        etcd_password: str | None = None,
        etcd_client: Any | None = None,
    ) -> None:
        self._working: SharedMemoryBackend = working or InMemoryBackend()
        self._short_term: SharedMemoryBackend = short_term or InMemoryBackend()
        self._long_term: SharedMemoryBackend = long_term or self._build_long_term_backend(
            long_term_backend=long_term_backend,
            db_path=db_path,
            etcd_host=etcd_host,
            etcd_port=etcd_port,
            etcd_namespace=etcd_namespace,
            etcd_timeout_s=etcd_timeout_s,
            etcd_user=etcd_user,
            etcd_password=etcd_password,
            etcd_client=etcd_client,
        )
        self._short_term_ttl_s = short_term_ttl_s

    @staticmethod
    def _build_long_term_backend(
        *,
        long_term_backend: str,
        db_path: str,
        etcd_host: str,
        etcd_port: int,
        etcd_namespace: str,
        etcd_timeout_s: float,
        etcd_user: str | None,
        etcd_password: str | None,
        etcd_client: Any | None,
    ) -> SharedMemoryBackend:
        backend_name = long_term_backend.strip().lower()

        if backend_name == "sqlite":
            return SQLiteBackend(db_path)
        if backend_name == "etcd":
            return EtcdBackend(
                host=etcd_host,
                port=etcd_port,
                namespace=etcd_namespace,
                timeout_s=etcd_timeout_s,
                user=etcd_user,
                password=etcd_password,
                client=etcd_client,
            )

        raise ValueError(
            "long_term_backend must be 'sqlite' or 'etcd'"
        )

    # ── Working tier (per-agent, ephemeral) ───────────────────────────────

    def set_working(self, agent_id: str, key: str, value: Any) -> None:
        """Write *value* into the working-tier slot for *agent_id*."""
        self._working.set(f"working:{agent_id}:{key}", value)

    def get_working(self, agent_id: str, key: str) -> Any | None:
        """Read a working-tier value for *agent_id*. Returns None if absent."""
        return self._working.get(f"working:{agent_id}:{key}")

    def keys_working(self, agent_id: str) -> list[str]:
        """Return all working-tier keys for *agent_id* (stripped of prefix)."""
        prefix = f"working:{agent_id}:"
        return [k[len(prefix):] for k in self._working.keys(prefix)]

    def clear_working(self, agent_id: str) -> None:
        """Delete all working-tier entries for *agent_id* (GC on terminate)."""
        prefix = f"working:{agent_id}:"
        for full_key in self._working.keys(prefix):
            self._working.delete(full_key)

    def handoff(self, from_agent_id: str, to_agent_id: str) -> None:
        """Copy all working-tier keys from *from_agent_id* to *to_agent_id*.

        Analogous to a Kubernetes pod volume mount handoff — used when an
        idle agent hands its in-progress context to a freshly spawned agent.
        """
        prefix = f"working:{from_agent_id}:"
        for full_key in self._working.keys(prefix):
            key_suffix = full_key[len(prefix):]
            value = self._working.get(full_key)
            if value is not None:
                self.set_working(to_agent_id, key_suffix, value)

    # ── Short-term tier (session-scoped, TTL-bounded) ─────────────────────

    def set_short_term(self, domain: str, key: str, value: Any) -> None:
        """Write *value* into the short-term tier under *domain*."""
        self._short_term.set(
            f"short_term:{domain}:{key}", value, ttl_s=self._short_term_ttl_s
        )

    def get_short_term(self, domain: str, key: str) -> Any | None:
        """Read a short-term value. Returns None if absent or TTL expired."""
        return self._short_term.get(f"short_term:{domain}:{key}")

    def keys_short_term(self, domain: str) -> list[str]:
        """Return all live short-term keys for *domain*."""
        prefix = f"short_term:{domain}:"
        return [k[len(prefix):] for k in self._short_term.keys(prefix)]

    # ── Long-term tier (blueprint-scoped, persistent) ─────────────────────

    def set_long_term(self, blueprint: str, key: str, value: Any) -> None:
        """Write *value* into the long-term tier under *blueprint*."""
        self._long_term.set(f"long_term:{blueprint}:{key}", value)

    def get_long_term(self, blueprint: str, key: str) -> Any | None:
        """Read a long-term value. Returns None if absent."""
        return self._long_term.get(f"long_term:{blueprint}:{key}")

    def keys_long_term(self, blueprint: str) -> list[str]:
        """Return all long-term keys for *blueprint* (stripped of prefix)."""
        prefix = f"long_term:{blueprint}:"
        return [k[len(prefix):] for k in self._long_term.keys(prefix)]

    def delete_long_term(self, blueprint: str, key: str) -> bool:
        """Remove a single long-term key. Returns True if it existed."""
        return self._long_term.delete(f"long_term:{blueprint}:{key}")

    def __repr__(self) -> str:
        return (
            f"SharedMemory("
            f"working={self._working!r}, "
            f"short_term={self._short_term!r}, "
            f"long_term={self._long_term!r})"
        )
