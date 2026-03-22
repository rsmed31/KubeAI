"""Tests for Prometheus exporter."""

from KubeAI.monitoring.metrics import MetricsStore
from KubeAI.monitoring.prometheus_exporter import PrometheusExporter


def test_exporter_creates():
    store = MetricsStore()
    exporter = PrometheusExporter(store)
    assert exporter is not None


def test_exporter_empty_store():
    store = MetricsStore()
    exporter = PrometheusExporter(store)
    output = exporter.generate()
    assert isinstance(output, bytes)


def test_exporter_with_counter():
    store = MetricsStore()
    store.inc_counter("kubeai_tasks_total", labels={"blueprint": "test", "status": "success"})
    store.inc_counter("kubeai_tasks_total", labels={"blueprint": "test", "status": "success"})

    exporter = PrometheusExporter(store)
    output = exporter.generate().decode("utf-8")
    assert "kubeai_tasks_total" in output


def test_exporter_with_gauge():
    store = MetricsStore()
    store.set_gauge("kubeai_agent_pool_size", 5, labels={"blueprint": "coding", "state": "running"})

    exporter = PrometheusExporter(store)
    output = exporter.generate().decode("utf-8")
    assert "kubeai_agent_pool_size" in output


def test_exporter_with_histogram():
    store = MetricsStore()
    store.observe_histogram("kubeai_task_latency_ms", 100.0, labels={"blueprint": "test"})
    store.observe_histogram("kubeai_task_latency_ms", 200.0, labels={"blueprint": "test"})

    exporter = PrometheusExporter(store)
    output = exporter.generate().decode("utf-8")
    assert "kubeai_task_latency_ms" in output


def test_exporter_content_type():
    store = MetricsStore()
    exporter = PrometheusExporter(store)
    ct = exporter.content_type()
    assert "text/plain" in ct


def test_exporter_sanitize_name():
    assert PrometheusExporter._sanitize_name("valid_name") == "valid_name"
    assert PrometheusExporter._sanitize_name("has-dash") == "has_dash"
    assert PrometheusExporter._sanitize_name("has.dot") == "has_dot"


def test_exporter_multiple_labels():
    store = MetricsStore()
    store.inc_counter("multi", labels={"a": "1", "b": "2"})
    store.set_gauge("multi_g", 10, labels={"x": "y"})

    exporter = PrometheusExporter(store)
    output = exporter.generate()
    assert isinstance(output, bytes)
    assert len(output) > 0


def test_exporter_repr():
    store = MetricsStore()
    exporter = PrometheusExporter(store)
    r = repr(exporter)
    assert "PrometheusExporter" in r
    assert "backend=" in r


def test_exporter_histogram_aggregated_fields():
    """Verify histogram sync produces _count, _sum, _min, _max gauges."""
    store = MetricsStore()
    store.observe_histogram("latency", 10.0, labels={"bp": "x"})
    store.observe_histogram("latency", 30.0, labels={"bp": "x"})

    exporter = PrometheusExporter(store)
    output = exporter.generate().decode("utf-8")
    assert "latency_count" in output
    assert "latency_sum" in output
    assert "latency_min" in output
    assert "latency_max" in output


def test_exporter_counter_value_reflected():
    """Counter value should be the cumulative total, not a delta."""
    store = MetricsStore()
    store.inc_counter("ops", 3.0)
    store.inc_counter("ops", 7.0)

    exporter = PrometheusExporter(store)
    output = exporter.generate().decode("utf-8")
    assert "ops" in output
    # The value should be 10.0
    assert "10.0" in output


def test_exporter_gauge_no_labels():
    store = MetricsStore()
    store.set_gauge("simple_gauge", 42.0)

    exporter = PrometheusExporter(store)
    output = exporter.generate().decode("utf-8")
    assert "simple_gauge" in output
    assert "42.0" in output
