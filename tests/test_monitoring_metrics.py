"""Unit tests for MetricsStore: Prometheus-style counters, gauges, histograms, and text rendering."""

from __future__ import annotations

import pytest

from KubeAI.monitoring import HistogramSample, MetricsStore


class TestMetricsStore:
    def test_counter_increment_and_readback(self) -> None:
        store = MetricsStore()

        first = store.inc_counter("KubeAI_tasks_total", labels={"blueprint": "research", "status": "ok"})
        second = store.inc_counter(
            "KubeAI_tasks_total",
            value=2,
            labels={"status": "ok", "blueprint": "research"},
        )

        assert first == 1.0
        assert second == 3.0
        assert (
            store.get_counter(
                "KubeAI_tasks_total",
                labels={"blueprint": "research", "status": "ok"},
            )
            == 3.0
        )

    def test_counter_rejects_negative_increment(self) -> None:
        store = MetricsStore()

        with pytest.raises(ValueError, match="non-negative"):
            store.inc_counter("KubeAI_tasks_total", value=-1.0)

    def test_gauge_set_and_readback(self) -> None:
        store = MetricsStore()

        store.set_gauge(
            "KubeAI_agent_pool_size",
            value=4,
            labels={"blueprint": "coding_agent", "state": "running"},
        )

        assert (
            store.get_gauge(
                "KubeAI_agent_pool_size",
                labels={"blueprint": "coding_agent", "state": "running"},
            )
            == 4.0
        )

    def test_histogram_aggregate_updates(self) -> None:
        store = MetricsStore()

        sample_1 = store.observe_histogram("KubeAI_task_latency_ms", value=100.0)
        sample_2 = store.observe_histogram("KubeAI_task_latency_ms", value=50.0)

        assert sample_1 == HistogramSample(count=1, total=100.0, minimum=100.0, maximum=100.0)
        assert sample_2 == HistogramSample(count=2, total=150.0, minimum=50.0, maximum=100.0)
        assert store.get_histogram("KubeAI_task_latency_ms") == sample_2

    def test_snapshot_and_prometheus_render(self) -> None:
        store = MetricsStore()
        store.inc_counter("KubeAI_tasks_total", labels={"blueprint": "research", "status": "ok"})
        store.set_gauge("KubeAI_agent_pool_size", value=3, labels={"blueprint": "research", "state": "running"})
        store.observe_histogram("KubeAI_eval_score", value=0.91, labels={"blueprint": "research"})

        snapshot = store.snapshot()

        assert len(snapshot["counters"]) == 1
        assert len(snapshot["gauges"]) == 1
        assert len(snapshot["histograms"]) == 1

        text = store.render_prometheus_text()
        assert 'KubeAI_tasks_total{blueprint="research",status="ok"} 1.0' in text
        assert 'KubeAI_agent_pool_size{blueprint="research",state="running"} 3.0' in text
        assert 'KubeAI_eval_score_count{blueprint="research"} 1.0' in text

    def test_repr_has_bucket_counts(self) -> None:
        store = MetricsStore()
        store.inc_counter("counter")
        store.set_gauge("gauge", 1)
        store.observe_histogram("hist", 2)

        text = repr(store)
        assert "counters=1" in text
        assert "gauges=1" in text
        assert "histograms=1" in text
