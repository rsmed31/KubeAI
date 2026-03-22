"""AdapterRegistry — lookup adapters by name."""

from __future__ import annotations

import threading
from typing import Iterator

from KubeAI.adapters.base import OrchestrationAdapter


class AdapterRegistry:
    """Thread-safe registry mapping framework names to adapter instances."""

    def __init__(self) -> None:
        self._adapters: dict[str, OrchestrationAdapter] = {}
        self._lock = threading.RLock()

    def register(self, adapter: OrchestrationAdapter) -> None:
        with self._lock:
            self._adapters[adapter.name] = adapter

    def get(self, name: str) -> OrchestrationAdapter:
        with self._lock:
            if name not in self._adapters:
                raise KeyError(f"Adapter {name!r} not registered")
            return self._adapters[name]

    def list_adapters(self) -> list[OrchestrationAdapter]:
        with self._lock:
            return list(self._adapters.values())

    def list_names(self) -> list[str]:
        with self._lock:
            return sorted(self._adapters.keys())

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._adapters

    def healthy_adapters(self) -> list[OrchestrationAdapter]:
        with self._lock:
            return [a for a in self._adapters.values() if a.health_check()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._adapters)

    def __iter__(self) -> Iterator[OrchestrationAdapter]:
        with self._lock:
            return iter(list(self._adapters.values()))

    def __repr__(self) -> str:
        with self._lock:
            return f"AdapterRegistry(adapters={list(self._adapters.keys())})"
