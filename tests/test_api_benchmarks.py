"""Integration tests — benchmarks API routes via FastAPI TestClient.

The BenchmarkEngine is wired as a real in-memory instance.  Adapter invocations
are short-circuited by a stub adapter so no LLM HTTP calls are made.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.adapters.registry import AdapterRegistry
from KubeAI.benchmarks.engine import BenchmarkEngine
from KubeAI.dashboard.api.benchmarks import router as benchmarks_router
from KubeAI.dashboard.deps import get_runtime


# ---------------------------------------------------------------------------
# Stub adapter — returns a canned response; no HTTP calls
# ---------------------------------------------------------------------------

class _StubAdapter(OrchestrationAdapter):
    """Returns a deterministic canned text so scenarios can evaluate it."""

    @property
    def name(self) -> str:
        return "litellm"

    def invoke(
        self,
        *,
        task: str,
        system_prompt: str,
        model_id: str,
        **kwargs,
    ) -> AdapterResult:
        # Return a response that contains keywords likely to score above 0
        return AdapterResult(
            text=(
                "LlamaIndex is used for building RAG pipelines and retrieval systems. "
                "It provides tools for indexing documents, querying vector stores, and "
                "connecting large language models to external data sources."
            ),
            latency_ms=10.0,
            token_cost=0.0002,
            framework="litellm",
        )


# ---------------------------------------------------------------------------
# Minimal Runtime stub — only the fields consumed by the benchmarks router
# ---------------------------------------------------------------------------

class _MinimalRuntime:
    """Provides just the fields that trigger_benchmark accesses on Runtime."""

    def __init__(self, engine: BenchmarkEngine, registry: AdapterRegistry) -> None:
        self.benchmark_engine = engine
        self.adapter_registry = registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine() -> BenchmarkEngine:
    return BenchmarkEngine()


@pytest.fixture()
def adapter_registry() -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(_StubAdapter())
    return reg


@pytest.fixture()
def client(engine: BenchmarkEngine, adapter_registry: AdapterRegistry) -> TestClient:
    """Build a minimal FastAPI app with the benchmarks router and patched deps.

    The benchmarks router has two Depends() chains that both root at get_runtime:
      - list_runs / get_run / leaderboard / recommendations: Depends(_get_engine)
        which itself Depends(get_runtime)
      - trigger_benchmark: Depends(get_runtime) directly (needs runtime.adapter_registry)

    Overriding get_runtime in dependency_overrides satisfies both chains.
    """
    app = FastAPI()
    app.include_router(benchmarks_router, prefix="/api")

    runtime = _MinimalRuntime(engine, adapter_registry)

    # get_runtime is the single root dependency used by all benchmarks routes.
    # Overriding it here causes FastAPI to inject our stub runtime for every
    # request, which provides both runtime.benchmark_engine and
    # runtime.adapter_registry without touching the production singleton.
    app.dependency_overrides[get_runtime] = lambda: runtime

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Test 1: GET /api/benchmarks/runs returns a list (empty is fine)
# ---------------------------------------------------------------------------

def test_list_runs_returns_empty_list_initially(client: TestClient) -> None:
    """GET /api/benchmarks/runs returns 200 and an empty list before any runs."""
    response = client.get("/api/benchmarks/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 0


# ---------------------------------------------------------------------------
# Test 2: GET /api/benchmarks/leaderboard returns a list
# ---------------------------------------------------------------------------

def test_get_leaderboard_returns_list(client: TestClient) -> None:
    """GET /api/benchmarks/leaderboard returns 200 and a list."""
    response = client.get("/api/benchmarks/leaderboard")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Test 3: GET /api/benchmarks/recommendations returns a dict
# ---------------------------------------------------------------------------

def test_get_recommendations_returns_dict(client: TestClient) -> None:
    """GET /api/benchmarks/recommendations returns 200 and a dict."""
    response = client.get("/api/benchmarks/recommendations")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


# ---------------------------------------------------------------------------
# Test 4: POST /api/benchmarks/run with valid scenario + framework -> results
# ---------------------------------------------------------------------------

def test_trigger_benchmark_run_returns_results(client: TestClient) -> None:
    """POST /api/benchmarks/run with a known scenario returns result records."""
    response = client.post(
        "/api/benchmarks/run",
        json={"scenario": "rag", "framework": "litellm", "num_runs": 1},
    )
    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)
    assert len(results) == 1

    record = results[0]
    assert "run_id" in record
    assert record["scenario"] == "rag"
    assert record["framework"] == "litellm"
    assert "quality_score" in record
    assert "latency_ms" in record
    assert "token_cost" in record
    assert "output_text" in record
    assert "recorded_at" in record
    assert 0.0 <= record["quality_score"] <= 1.0


# ---------------------------------------------------------------------------
# Test 5: POST /api/benchmarks/run with unknown scenario returns 400
# ---------------------------------------------------------------------------

def test_trigger_benchmark_run_unknown_scenario_returns_400(client: TestClient) -> None:
    """POST /api/benchmarks/run with an unknown scenario name returns 400."""
    response = client.post(
        "/api/benchmarks/run",
        json={"scenario": "nonexistent_scenario", "framework": "litellm", "num_runs": 1},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Test 6: POST /api/benchmarks/run with unknown framework returns 404
# ---------------------------------------------------------------------------

def test_trigger_benchmark_run_unknown_framework_returns_404(client: TestClient) -> None:
    """POST /api/benchmarks/run with an unregistered framework returns 404."""
    response = client.post(
        "/api/benchmarks/run",
        json={"scenario": "rag", "framework": "nonexistent_fw", "num_runs": 1},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: Runs accumulate and appear in /runs after a benchmark
# ---------------------------------------------------------------------------

def test_runs_accumulate_after_benchmark(client: TestClient) -> None:
    """After a benchmark run, /api/benchmarks/runs returns the new records."""
    client.post(
        "/api/benchmarks/run",
        json={"scenario": "codegen", "framework": "litellm", "num_runs": 2},
    )
    response = client.get("/api/benchmarks/runs")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) >= 2
    scenarios = {r["scenario"] for r in runs}
    assert "codegen" in scenarios


# ---------------------------------------------------------------------------
# Test 8: Leaderboard is populated after a benchmark run
# ---------------------------------------------------------------------------

def test_leaderboard_populated_after_run(client: TestClient) -> None:
    """After running a benchmark, the leaderboard has at least one entry."""
    client.post(
        "/api/benchmarks/run",
        json={"scenario": "research", "framework": "litellm", "num_runs": 1},
    )
    response = client.get("/api/benchmarks/leaderboard")
    lb = response.json()
    assert len(lb) >= 1
    entry = lb[0]
    assert "framework" in entry
    assert "scenario" in entry
    assert "avg_quality_score" in entry
    assert "num_runs" in entry


# ---------------------------------------------------------------------------
# Test 9: Recommendations populated after benchmark run
# ---------------------------------------------------------------------------

def test_recommendations_populated_after_run(client: TestClient) -> None:
    """After a rag benchmark, recommendations includes an entry for 'rag'."""
    client.post(
        "/api/benchmarks/run",
        json={"scenario": "rag", "framework": "litellm", "num_runs": 1},
    )
    response = client.get("/api/benchmarks/recommendations")
    recs = response.json()
    assert isinstance(recs, dict)
    assert "rag" in recs
    assert recs["rag"] == "litellm"


# ---------------------------------------------------------------------------
# Test 10: GET /api/benchmarks/runs/{run_id} returns the specific record
# ---------------------------------------------------------------------------

def test_get_run_by_id_returns_correct_record(client: TestClient) -> None:
    """GET /api/benchmarks/runs/{run_id} returns the record with the matching ID."""
    run_resp = client.post(
        "/api/benchmarks/run",
        json={"scenario": "data_analysis", "framework": "litellm", "num_runs": 1},
    )
    run_id = run_resp.json()[0]["run_id"]

    response = client.get(f"/api/benchmarks/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    assert response.json()["scenario"] == "data_analysis"


# ---------------------------------------------------------------------------
# Test 11: GET /api/benchmarks/runs/{run_id} for unknown ID returns 404
# ---------------------------------------------------------------------------

def test_get_run_by_nonexistent_id_returns_404(client: TestClient) -> None:
    """GET /api/benchmarks/runs/{run_id} returns 404 for an unknown run_id."""
    response = client.get("/api/benchmarks/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
