"""Tracer is the Jaeger/OpenTelemetry analogue: lightweight in-process span tree for KubeAI request tracing."""

from __future__ import annotations

import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    """A single unit of traced work."""

    name: str
    trace_id: str
    span_id: str
    parent_id: str | None
    started_at: float
    ended_at: float | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # ok | error

    def finish(self, *, status: str = "ok") -> None:
        """Mark span as complete."""
        self.ended_at = time.time()
        self.status = status

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000

    def __repr__(self) -> str:
        dur = f"{self.duration_ms:.1f}ms" if self.duration_ms is not None else "open"
        return f"Span(name={self.name!r}, status={self.status!r}, duration={dur})"


class Tracer:
    """
    In-process tracer — collects spans for a single trace.

    with tracer.start_span("route") as span:
        span.tags["blueprint"] = "coding_agent"
    """

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex
        self._spans: list[Span] = []
        self._lock = threading.RLock()
        self._active: threading.local = threading.local()

    def start_span(self, name: str, tags: dict[str, Any] | None = None) -> Span:
        """Create and record a new span. Call span.finish() when done."""
        parent_id = getattr(self._active, "current_span_id", None)
        span = Span(
            name=name,
            trace_id=self.trace_id,
            span_id=uuid.uuid4().hex[:12],
            parent_id=parent_id,
            started_at=time.time(),
            tags=dict(tags or {}),
        )
        with self._lock:
            self._spans.append(span)
        self._active.current_span_id = span.span_id
        return span

    def spans(self) -> list[Span]:
        with self._lock:
            return list(self._spans)

    def finished_spans(self) -> list[Span]:
        with self._lock:
            return [s for s in self._spans if s.ended_at is not None]

    def __repr__(self) -> str:
        with self._lock:
            return f"Tracer(trace_id={self.trace_id!r}, spans={len(self._spans)})"


_default_tracer: Tracer | None = None
_tracer_lock = threading.Lock()


def get_tracer() -> Tracer:
    """Return or create the process-wide default tracer."""
    global _default_tracer
    with _tracer_lock:
        if _default_tracer is None:
            _default_tracer = Tracer()
        return _default_tracer
