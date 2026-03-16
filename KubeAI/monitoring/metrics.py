"""Metrics store is the Prometheus-scrape analogue that tracks runtime counters, gauges, and histograms for KubeAI control-plane operations."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Mapping


LabelSet = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class HistogramSample:
    """Aggregated histogram state for one metric name + label set."""

    count: int
    total: float
    minimum: float
    maximum: float


class MetricsStore:
    """In-memory metrics registry with Prometheus-style text rendering."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, LabelSet], float] = {}
        self._gauges: dict[tuple[str, LabelSet], float] = {}
        self._histograms: dict[tuple[str, LabelSet], list[float]] = {}
        self._lock = threading.RLock()

    def inc_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        """Increment a counter and return its new value."""
        if value < 0:
            raise ValueError("counter increment value must be non-negative")

        key = self._metric_key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)
            return self._counters[key]

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        """Set a gauge and return its stored value."""
        key = self._metric_key(name, labels)
        with self._lock:
            self._gauges[key] = float(value)
            return self._gauges[key]

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> HistogramSample:
        """Observe one histogram value and return its updated aggregate."""
        key = self._metric_key(name, labels)
        with self._lock:
            points = self._histograms.setdefault(key, [])
            points.append(float(value))
            return self._histogram_sample(points)

    def get_counter(
        self,
        name: str,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        """Return counter value or 0.0 when absent."""
        key = self._metric_key(name, labels)
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_gauge(
        self,
        name: str,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        """Return gauge value or 0.0 when absent."""
        key = self._metric_key(name, labels)
        with self._lock:
            return self._gauges.get(key, 0.0)

    def get_histogram(
        self,
        name: str,
        labels: Mapping[str, str] | None = None,
    ) -> HistogramSample | None:
        """Return histogram aggregate or None when absent."""
        key = self._metric_key(name, labels)
        with self._lock:
            points = self._histograms.get(key)
            if not points:
                return None
            return self._histogram_sample(points)

    def snapshot(self) -> dict[str, list[dict[str, object]]]:
        """Return a stable snapshot suitable for API responses."""
        with self._lock:
            counters = [
                {
                    "name": name,
                    "labels": dict(labels),
                    "value": value,
                }
                for (name, labels), value in sorted(self._counters.items())
            ]
            gauges = [
                {
                    "name": name,
                    "labels": dict(labels),
                    "value": value,
                }
                for (name, labels), value in sorted(self._gauges.items())
            ]
            histograms = [
                {
                    "name": name,
                    "labels": dict(labels),
                    "count": sample.count,
                    "sum": sample.total,
                    "min": sample.minimum,
                    "max": sample.maximum,
                }
                for (name, labels), points in sorted(self._histograms.items())
                for sample in [self._histogram_sample(points)]
            ]

        return {
            "counters": counters,
            "gauges": gauges,
            "histograms": histograms,
        }

    def render_prometheus_text(self) -> str:
        """Render current metric values in a Prometheus-like exposition format."""
        lines: list[str] = []
        snapshot = self.snapshot()

        for item in snapshot["counters"]:
            lines.append(self._render_sample(item["name"], item["value"], item["labels"]))

        for item in snapshot["gauges"]:
            lines.append(self._render_sample(item["name"], item["value"], item["labels"]))

        for item in snapshot["histograms"]:
            name = str(item["name"])
            labels = item["labels"]
            lines.append(self._render_sample(f"{name}_count", item["count"], labels))
            lines.append(self._render_sample(f"{name}_sum", item["sum"], labels))
            lines.append(self._render_sample(f"{name}_min", item["min"], labels))
            lines.append(self._render_sample(f"{name}_max", item["max"], labels))

        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _metric_key(name: str, labels: Mapping[str, str] | None) -> tuple[str, LabelSet]:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("metric name must not be empty")

        if labels is None:
            return normalized_name, ()

        normalized_labels: list[tuple[str, str]] = []
        for key, value in sorted(labels.items()):
            label_key = str(key).strip()
            if not label_key:
                raise ValueError("label key must not be empty")
            normalized_labels.append((label_key, str(value)))

        return normalized_name, tuple(normalized_labels)

    @staticmethod
    def _histogram_sample(points: list[float]) -> HistogramSample:
        return HistogramSample(
            count=len(points),
            total=float(sum(points)),
            minimum=float(min(points)),
            maximum=float(max(points)),
        )

    @staticmethod
    def _render_sample(name: object, value: object, labels: object) -> str:
        metric_name = str(name)
        metric_value = float(value)
        label_text = MetricsStore._labels_to_text(labels)
        return f"{metric_name}{label_text} {metric_value}"

    @staticmethod
    def _labels_to_text(labels: object) -> str:
        if not isinstance(labels, dict) or not labels:
            return ""
        parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(parts) + "}"

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"MetricsStore(counters={len(self._counters)}, "
                f"gauges={len(self._gauges)}, histograms={len(self._histograms)})"
            )
