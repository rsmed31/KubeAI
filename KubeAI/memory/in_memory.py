"""InMemoryBackend is the tmpfs analogue: fast volatile storage for working-tier agent state."""

from __future__ import annotations

import threading
import time
from typing import Any

from .base import SharedMemoryBackend


class InMemoryBackend(SharedMemoryBackend):
    """Thread-safe in-process KV store with optional per-key TTL.

    Analogous to a Kubernetes emptyDir volume — data lives only as long as
    the process (or agent) that owns it.
    """

    def __init__(self) -> None:
        # Each slot is (value, expires_at | None)
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        """Return value for *key*, or None if absent or TTL has expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        """Store *value* under *key* with an optional TTL in seconds."""
        expires_at = (time.monotonic() + ttl_s) if ttl_s is not None else None
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """Remove *key*. Returns True if it existed."""
        with self._lock:
            return self._store.pop(key, None) is not None

    def keys(self, prefix: str = "") -> list[str]:
        """Return all live (non-expired) keys, optionally filtered by prefix."""
        now = time.monotonic()
        with self._lock:
            expired = [
                k for k, (_, exp) in self._store.items()
                if exp is not None and now >= exp
            ]
            for k in expired:
                del self._store[k]
            return [k for k in self._store if k.startswith(prefix)]

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self.keys())

    def __repr__(self) -> str:
        with self._lock:
            return f"InMemoryBackend(entries={len(self._store)})"
