"""SharedMemoryBackend is the etcd analogue: persistent distributed state store backing agent working, short-term, and long-term memory tiers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SharedMemoryBackend(ABC):
    """Abstract base for pluggable KV storage backends used by SharedMemory tiers."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Return the stored value for *key*, or None if absent or expired."""

    @abstractmethod
    def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        """Store *value* under *key*. Optional *ttl_s* sets seconds-to-live."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove *key*. Returns True if the key existed, False otherwise."""

    @abstractmethod
    def keys(self, prefix: str = "") -> list[str]:
        """Return all live keys (not expired) optionally filtered by prefix."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all keys from this backend."""

    @abstractmethod
    def __repr__(self) -> str: ...
