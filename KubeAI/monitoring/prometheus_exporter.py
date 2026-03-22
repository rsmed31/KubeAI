"""Prometheus exporter -- bridges MetricsStore to prometheus_client for proper scraping."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from KubeAI.monitoring.metrics import MetricsStore

try:
    from prometheus_client import (
        CollectorRegistry,
        Gauge,
        generate_latest,
    )

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


class PrometheusExporter:
    """Syncs MetricsStore state to prometheus_client objects for proper scraping.

    When prometheus_client is not installed, falls back to MetricsStore's
    built-in render_prometheus_text() method.
    """

    def __init__(self, metrics_store: "MetricsStore") -> None:
        self._store = metrics_store
        self._lock = threading.Lock()

        if HAS_PROMETHEUS:
            self._registry = CollectorRegistry()
            self._gauges: dict[str, Gauge] = {}
        else:
            self._registry = None

    def generate(self) -> bytes:
        """Generate Prometheus exposition format bytes.

        Returns bytes suitable for HTTP response with
        Content-Type: text/plain; version=0.0.4; charset=utf-8
        """
        if not HAS_PROMETHEUS:
            return self._store.render_prometheus_text().encode("utf-8")

        self._sync()
        return generate_latest(self._registry)

    def content_type(self) -> str:
        """Return the proper Content-Type header value."""
        if HAS_PROMETHEUS:
            return "text/plain; version=0.0.4; charset=utf-8"
        return "text/plain; charset=utf-8"

    def _sync(self) -> None:
        """Sync MetricsStore snapshot to prometheus_client objects.

        All MetricsStore values are exposed as Prometheus Gauge objects.
        Counters are gauges because MetricsStore counters report absolute
        values (not deltas), so a true prometheus_client Counter would
        double-count on each sync.  Histograms are pre-aggregated in
        MetricsStore, so they are emitted as ``<name>_count``,
        ``<name>_sum``, ``<name>_min``, and ``<name>_max`` gauges.
        """
        if not HAS_PROMETHEUS:
            return

        snapshot = self._store.snapshot()

        with self._lock:
            # Sync counters (exposed as gauges to preserve absolute values)
            for item in snapshot.get("counters", []):
                name = self._sanitize_name(str(item["name"]))
                labels = item.get("labels", {})
                label_names = sorted(labels.keys()) if labels else []
                label_values = tuple(labels[k] for k in label_names) if labels else ()

                gauge = self._get_or_create_gauge(name, label_names)
                if label_values:
                    gauge.labels(*label_values).set(float(item["value"]))
                else:
                    gauge.set(float(item["value"]))

            # Sync gauges
            for item in snapshot.get("gauges", []):
                name = self._sanitize_name(str(item["name"]))
                labels = item.get("labels", {})
                label_names = sorted(labels.keys()) if labels else []
                label_values = tuple(labels[k] for k in label_names) if labels else ()

                gauge = self._get_or_create_gauge(name, label_names)
                if label_values:
                    gauge.labels(*label_values).set(float(item["value"]))
                else:
                    gauge.set(float(item["value"]))

            # Sync histograms (as summary-style gauges since we have pre-aggregated data)
            for item in snapshot.get("histograms", []):
                name = self._sanitize_name(str(item["name"]))
                labels = item.get("labels", {})
                label_names = sorted(labels.keys()) if labels else []
                label_values = tuple(labels[k] for k in label_names) if labels else ()

                for suffix, value in [
                    ("_count", item["count"]),
                    ("_sum", item["sum"]),
                    ("_min", item.get("min", 0)),
                    ("_max", item.get("max", 0)),
                ]:
                    g = self._get_or_create_gauge(f"{name}{suffix}", label_names)
                    if label_values:
                        g.labels(*label_values).set(float(value))
                    else:
                        g.set(float(value))

    def _get_or_create_gauge(self, name: str, label_names: list[str]) -> "Gauge":
        """Return an existing Gauge or create a new one in the private registry."""
        key = name
        if key not in self._gauges:
            self._gauges[key] = Gauge(
                name,
                f"KubeAI metric: {name}",
                labelnames=label_names,
                registry=self._registry,
            )
        return self._gauges[key]

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize metric name for Prometheus (only [a-zA-Z0-9_:])."""
        return "".join(c if c.isalnum() or c in "_:" else "_" for c in name)

    def __repr__(self) -> str:
        backend = "prometheus_client" if HAS_PROMETHEUS else "fallback"
        return f"PrometheusExporter(backend={backend})"
