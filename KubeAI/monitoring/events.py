"""Event stream hub is the Kubernetes events analogue that records control-plane lifecycle events for API/UI consumers."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuntimeEvent:
    """Immutable runtime event record for task and agent lifecycle tracing."""

    event_id: str
    event_type: str
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)


class EventStreamHub:
    """Thread-safe in-memory event stream with incremental ids."""

    def __init__(self, max_events: int = 5000) -> None:
        self._max_events = max(1, max_events)
        self._events: deque[RuntimeEvent] = deque(maxlen=self._max_events)
        self._next_id: int = 1
        self._lock = threading.RLock()

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> RuntimeEvent:
        """Publish one runtime event and return the stored record."""
        event_name = event_type.strip()
        if not event_name:
            raise ValueError("event_type must not be empty")

        with self._lock:
            event = RuntimeEvent(
                event_id=f"evt-{self._next_id}",
                event_type=event_name,
                timestamp=time.time(),
                payload=dict(payload or {}),
            )
            self._events.append(event)
            self._next_id += 1
            return event

    def list_events(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        after_event_id: str | None = None,
    ) -> list[RuntimeEvent]:
        """Return events in chronological order with optional type and cursor filtering."""
        max_items = max(1, limit)
        event_filter = event_type.strip() if event_type is not None else None
        min_id = self._parse_event_id(after_event_id)

        with self._lock:
            events = list(self._events)

        filtered: list[RuntimeEvent] = []
        for event in events:
            numeric_id = self._parse_event_id(event.event_id) or 0
            if min_id is not None and numeric_id <= min_id:
                continue
            if event_filter and event.event_type != event_filter:
                continue
            filtered.append(event)

        if len(filtered) <= max_items:
            return filtered
        return filtered[-max_items:]

    def latest_event_id(self) -> str | None:
        """Return the latest event id if any events are present."""
        with self._lock:
            if not self._events:
                return None
            return self._events[-1].event_id

    @staticmethod
    def _parse_event_id(event_id: str | None) -> int | None:
        if event_id is None:
            return None
        value = event_id.strip()
        if not value:
            return None
        if value.startswith("evt-"):
            value = value[4:]
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Invalid event id: {event_id!r}") from exc

    def __repr__(self) -> str:
        with self._lock:
            latest = self._events[-1].event_id if self._events else None
            return (
                f"EventStreamHub(max_events={self._max_events}, "
                f"stored_events={len(self._events)}, latest={latest!r})"
            )
