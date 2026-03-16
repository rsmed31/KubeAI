"""Monitoring API — the Prometheus/Grafana analogue for KubeAI metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import get_control_plane

router = APIRouter()


@router.get("/monitoring/metrics")
def get_metrics(cp: ControlPlaneAPI = Depends(get_control_plane)) -> dict:
    """Return all KubeAI metrics as a structured JSON snapshot.

    Analogous to a Prometheus /api/v1/query_range endpoint — returns
    the full metrics store snapshot for rendering in the monitoring dashboard.
    """
    return cp.metrics_snapshot()


@router.get("/monitoring/metrics/prometheus", response_class=PlainTextResponse)
def get_metrics_prometheus(cp: ControlPlaneAPI = Depends(get_control_plane)) -> str:
    """Return Prometheus text-format metrics for scraping.

    Analogous to the standard /metrics endpoint expected by Prometheus
    and compatible scrapers.
    """
    return cp.metrics_text()
