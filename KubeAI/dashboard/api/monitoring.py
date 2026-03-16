"""Monitoring API — the Prometheus/Grafana analogue for KubeAI metrics endpoints."""
from fastapi import APIRouter
from ..state import RuntimeState

router = APIRouter()


@router.get("/monitoring/metrics")
def get_metrics() -> dict:
    """Return the last 30 time-series data points for all KubeAI metrics.

    Analogous to a Prometheus query_range endpoint — returns historical
    metric data for rendering in the monitoring dashboard.
    """
    state = RuntimeState()
    snap = state.snapshot()
    return snap["metrics"]
