"""Orchestrator API — view and configure the semantic task router at runtime.

  GET  /api/orchestrator         → current config + stats
  PATCH /api/orchestrator        → update routing model override / thresholds
  GET  /api/orchestrator/decisions → recent routing decisions
  POST /api/orchestrator/test    → dry-run route a task (no execution)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from KubeAI.dashboard.deps import Runtime, get_runtime

router = APIRouter()


# ── GET /api/orchestrator ────────────────────────────────────────────────────

@router.get("/orchestrator")
def get_orchestrator(runtime: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    """Return current orchestrator config and pool summary."""
    cfg = runtime.orchestrator.get_config()
    return cfg


# ── PATCH /api/orchestrator ──────────────────────────────────────────────────

class OrchestratorUpdateRequest(BaseModel):
    routing_model_override: str | None = Field(
        default=...,
        description="Model ID to pin for routing, or null to auto-select the largest.",
    )
    min_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Minimum score threshold; tasks failing it are rejected.",
    )
    decompose_enabled: bool | None = Field(
        default=None,
        description="Enable/disable task decomposition.",
    )


@router.patch("/orchestrator")
def update_orchestrator(
    body: OrchestratorUpdateRequest,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    """Update mutable orchestrator settings without restarting."""
    try:
        runtime.orchestrator.update_config(
            routing_model_override=body.routing_model_override,
            min_confidence=body.min_confidence,
            decompose_enabled=body.decompose_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return runtime.orchestrator.get_config()


# ── GET /api/orchestrator/decisions ─────────────────────────────────────────

@router.get("/orchestrator/decisions")
def list_decisions(
    limit: int = 100,
    runtime: Runtime = Depends(get_runtime),
) -> list[dict[str, Any]]:
    """Return recent routing decisions (newest last)."""
    return runtime.control_plane.list_routing_decisions(limit=limit)


# ── POST /api/orchestrator/test ──────────────────────────────────────────────

class OrchestratorTestRequest(BaseModel):
    task: str = Field(..., description="Task description to route (dry-run, no execution).")
    blueprint: str | None = Field(default=None, description="Optional preferred blueprint to score against all candidates.")


@router.post("/orchestrator/test")
def test_route(
    body: OrchestratorTestRequest,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    """Dry-run route a task: score all blueprints and return ranked results without executing."""
    blueprints = runtime.registry.list_blueprints()
    if not blueprints:
        raise HTTPException(status_code=503, detail="No blueprints registered")

    try:
        cfg = runtime.orchestrator.get_config()
        routing_model_id = cfg["effective_routing_model"]
        # Score each blueprint individually for the ranking table
        from KubeAI.orchestrator.orchestrator import _llm_score
        scores = []
        for bp in blueprints:
            try:
                score = _llm_score(body.task, bp, routing_model_id)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Routing LLM error: {exc}")
            scores.append({"blueprint": bp.name, "description": bp.description,
                           "tier": bp.tier.value, "score": round(score, 4)})

        scores.sort(key=lambda x: -x["score"])
        winner = scores[0]["blueprint"] if scores else None
        return {
            "task": body.task,
            "routing_model": routing_model_id,
            "winner": winner,
            "scores": scores,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
