"""Sliding window memory is the rolling-update analogue that keeps only the most recent conversation slice."""

from __future__ import annotations

from typing import Any, MutableMapping, Sequence

from KubeAI.templates.base import Template


class SlidingWindowMemory(Template):
    """Keep the most recent fixed window of messages."""

    def __init__(self, window_size: int = 10) -> None:
        super().__init__(name="sliding_window")
        self.window_size = max(1, window_size)

    def __repr__(self) -> str:
        return f"SlidingWindowMemory(window_size={self.window_size})"

    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        self.configure(config)
        if config and "window_size" in config:
            self.window_size = max(1, int(config["window_size"]))
        setattr(agent, "memory_template", self)

    def apply(self, history: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        if not history:
            return []
        limit = min(self.window_size, len(history))
        return [dict(message) for message in history[-limit:]]
