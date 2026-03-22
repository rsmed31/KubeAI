"""Benchmarks API — run and inspect framework adapter benchmarks.

  GET  /api/benchmarks/runs              → list all stored run results
  GET  /api/benchmarks/runs/{run_id}     → detail for a single run
  POST /api/benchmarks/run               → trigger a benchmark run
  GET  /api/benchmarks/leaderboard       → aggregated scores per framework x scenario
  GET  /api/benchmarks/recommendations   → best framework per scenario type
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from KubeAI.benchmarks.engine import BenchmarkEngine
from KubeAI.dashboard.deps import Runtime, get_runtime

router = APIRouter(tags=["benchmarks"])


# ── Dependency: BenchmarkEngine from Runtime ──────────────────────────────────

def _get_engine(runtime: Runtime = Depends(get_runtime)) -> BenchmarkEngine:
    return runtime.benchmark_engine


# ── GET /api/benchmarks/runs ─────────────────────────────────────────────────

@router.get("/benchmarks/runs")
def list_runs(engine: BenchmarkEngine = Depends(_get_engine)) -> list[dict[str, Any]]:
    """Return all stored benchmark run results, newest first."""
    results = engine.get_results()
    return list(reversed(results))


# ── GET /api/benchmarks/runs/{run_id} ────────────────────────────────────────

@router.get("/benchmarks/runs/{run_id}")
def get_run(run_id: str, engine: BenchmarkEngine = Depends(_get_engine)) -> dict[str, Any]:
    """Return detail for a single benchmark run by its run_id."""
    record = engine.get_result(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return record


# ── POST /api/benchmarks/run ─────────────────────────────────────────────────

class BenchmarkRunRequest(BaseModel):
    scenario: str = Field(
        ...,
        description="Scenario name: 'rag', 'codegen', 'research', or 'data_analysis'.",
    )
    framework: str | None = Field(
        default=None,
        description=(
            "Framework adapter name to benchmark (e.g. 'litellm'). "
            "If omitted, all registered adapters are benchmarked."
        ),
    )
    num_runs: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of times to run each adapter against the scenario.",
    )


_SCENARIO_REGISTRY: dict[str, type] = {}


def _get_scenario_registry() -> dict[str, type]:
    """Lazy-build scenario registry to avoid import errors at module load."""
    global _SCENARIO_REGISTRY
    if _SCENARIO_REGISTRY:
        return _SCENARIO_REGISTRY
    from KubeAI.benchmarks.scenarios import (
        CodegenScenario,
        DataAnalysisScenario,
        RagScenario,
        ResearchScenario,
    )
    _SCENARIO_REGISTRY = {
        "rag": RagScenario,
        "codegen": CodegenScenario,
        "research": ResearchScenario,
        "data_analysis": DataAnalysisScenario,
    }
    return _SCENARIO_REGISTRY


@router.post("/benchmarks/run")
def trigger_benchmark(
    body: BenchmarkRunRequest,
    runtime: Runtime = Depends(get_runtime),
    engine: BenchmarkEngine = Depends(_get_engine),
) -> list[dict[str, Any]]:
    """Trigger a benchmark run synchronously and return the new result records."""
    registry = _get_scenario_registry()
    if body.scenario not in registry:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario {body.scenario!r}. Valid: {sorted(registry.keys())}",
        )

    scenario = registry[body.scenario]()

    # Resolve adapters
    from KubeAI.adapters.registry import AdapterRegistry

    adapter_registry: AdapterRegistry = getattr(runtime, "adapter_registry", None)
    if adapter_registry is None:
        # Fallback: use the LiteLLMAdapter directly
        from KubeAI.adapters.litellm_adapter import LiteLLMAdapter
        all_adapters = [LiteLLMAdapter()]
    else:
        all_adapters = adapter_registry.list_adapters()

    if body.framework is not None:
        adapters = [a for a in all_adapters if a.name == body.framework]
        if not adapters:
            raise HTTPException(
                status_code=404,
                detail=f"Framework adapter {body.framework!r} not registered.",
            )
    else:
        adapters = all_adapters

    if not adapters:
        raise HTTPException(status_code=503, detail="No adapters available to benchmark.")

    try:
        results = engine.run_benchmark(scenario, adapters, num_runs=body.num_runs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return results


# ── GET /api/benchmarks/leaderboard ──────────────────────────────────────────

@router.get("/benchmarks/leaderboard")
def get_leaderboard(engine: BenchmarkEngine = Depends(_get_engine)) -> list[dict[str, Any]]:
    """Return aggregated scores per (framework, scenario), sorted by quality descending."""
    return engine.get_leaderboard()


# ── GET /api/benchmarks/recommendations ──────────────────────────────────────

@router.get("/benchmarks/recommendations")
def get_recommendations(engine: BenchmarkEngine = Depends(_get_engine)) -> dict[str, str]:
    """Return the best framework name for each scenario type."""
    return engine.get_recommendations()
