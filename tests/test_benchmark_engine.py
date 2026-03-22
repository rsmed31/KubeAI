"""Tests for BenchmarkEngine, scenarios, and scorer."""

from __future__ import annotations

import pytest

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.benchmarks.engine import BenchmarkEngine
from KubeAI.benchmarks.scenarios import (
    BenchmarkScenario,
    CodegenScenario,
    DataAnalysisScenario,
    RagScenario,
    ResearchScenario,
)
from KubeAI.benchmarks.scorer import score_output


# ── Helpers ───────────────────────────────────────────────────────────────────

class _MockAdapter(OrchestrationAdapter):
    """Deterministic adapter that returns a fixed response."""

    def __init__(self, name: str, response: str) -> None:
        self._name = name
        self._response = response

    @property
    def name(self) -> str:
        return self._name

    def invoke(self, *, task: str, system_prompt: str, model_id: str, **kwargs) -> AdapterResult:
        return AdapterResult(
            text=self._response,
            latency_ms=42.0,
            token_cost=0.001,
            framework=self._name,
        )


# ── Test 1: BenchmarkScenario ABC is not instantiatable ──────────────────────

def test_benchmark_scenario_abc_not_instantiatable():
    """BenchmarkScenario is abstract and must not be directly instantiatable."""
    with pytest.raises(TypeError):
        BenchmarkScenario()  # type: ignore[abstract]


# ── Test 2: RagScenario.prepare() returns required keys ───────────────────────

def test_rag_scenario_prepare_has_required_keys():
    scenario = RagScenario()
    setup = scenario.prepare()
    assert "question" in setup
    assert "reference" in setup
    assert isinstance(setup["question"], str)
    assert isinstance(setup["reference"], str)
    assert len(setup["question"]) > 0
    assert len(setup["reference"]) > 0


# ── Test 3: CodegenScenario.prepare() returns required keys ───────────────────

def test_codegen_scenario_prepare_has_required_keys():
    scenario = CodegenScenario()
    setup = scenario.prepare()
    assert "task" in setup
    assert "keywords" in setup
    assert isinstance(setup["task"], str)
    assert isinstance(setup["keywords"], list)
    assert len(setup["keywords"]) > 0


# ── Test 4: ResearchScenario.prepare() returns required keys ──────────────────

def test_research_scenario_prepare_has_required_keys():
    scenario = ResearchScenario()
    setup = scenario.prepare()
    assert "topic" in setup
    assert "sections" in setup
    assert isinstance(setup["topic"], str)
    assert isinstance(setup["sections"], list)
    assert len(setup["sections"]) > 0


# ── Test 5: DataAnalysisScenario.prepare() returns required keys ──────────────

def test_data_analysis_scenario_prepare_has_required_keys():
    scenario = DataAnalysisScenario()
    setup = scenario.prepare()
    assert "data" in setup
    assert "question" in setup
    assert isinstance(setup["data"], str)
    assert isinstance(setup["question"], str)


# ── Test 6: scorer with reference ────────────────────────────────────────────

def test_score_output_with_reference_perfect_match():
    """Identical strings should yield Jaccard similarity of 1.0."""
    text = "the quick brown fox"
    score = score_output(text, reference=text)
    assert score == pytest.approx(1.0)


def test_score_output_with_reference_partial_match():
    """Partially overlapping strings yield a score in (0.0, 1.0)."""
    score = score_output("hello world foo", reference="hello world bar")
    assert 0.0 < score < 1.0


def test_score_output_with_reference_no_match():
    """Completely different word sets yield 0.0."""
    score = score_output("alpha beta gamma", reference="delta epsilon zeta")
    assert score == pytest.approx(0.0)


# ── Test 7: scorer without reference (fallback) ───────────────────────────────

def test_score_output_fallback_empty_string():
    """Empty output always scores 0.0."""
    assert score_output("") == pytest.approx(0.0)


def test_score_output_fallback_short_string():
    """Short output scores proportionally less than 1.0."""
    score = score_output("hi")
    assert 0.0 < score < 1.0


def test_score_output_fallback_long_string():
    """Output at or beyond 500 chars scores 1.0."""
    long_text = "x" * 500
    assert score_output(long_text) == pytest.approx(1.0)


def test_score_output_criteria_keyword_overlap():
    """Criteria-based scoring returns fraction of keywords present."""
    score = score_output("def fibonacci return", criteria="def fibonacci return")
    assert score == pytest.approx(1.0)

    score_partial = score_output("def something else", criteria="def fibonacci return")
    assert 0.0 < score_partial < 1.0


# ── Test 8: BenchmarkEngine.run_benchmark with mocked adapter ────────────────

def test_run_benchmark_returns_correct_structure():
    """run_benchmark should return result dicts with required keys."""
    engine = BenchmarkEngine()
    adapter = _MockAdapter("mock_fw", "This is a test response about LlamaIndex pipelines.")
    scenario = RagScenario()

    results = engine.run_benchmark(scenario, [adapter], num_runs=2)

    assert len(results) == 2
    for record in results:
        assert "run_id" in record
        assert "scenario" in record
        assert "framework" in record
        assert "quality_score" in record
        assert "latency_ms" in record
        assert "token_cost" in record
        assert "output_text" in record
        assert "recorded_at" in record
        assert record["scenario"] == "rag"
        assert record["framework"] == "mock_fw"
        assert 0.0 <= record["quality_score"] <= 1.0


def test_run_benchmark_stores_results():
    """Results should be accumulated in engine.get_results()."""
    engine = BenchmarkEngine()
    adapter = _MockAdapter("fw_a", "def fibonacci(n): return n")

    engine.run_benchmark(CodegenScenario(), [adapter], num_runs=1)
    all_results = engine.get_results()
    assert len(all_results) == 1
    assert all_results[0]["scenario"] == "codegen"


# ── Test 9: BenchmarkEngine.get_leaderboard returns correct structure ─────────

def test_get_leaderboard_structure():
    """Leaderboard should aggregate per (framework, scenario) and sort by score."""
    engine = BenchmarkEngine()
    adapter_a = _MockAdapter("fw_a", "attention encoder decoder transformer architecture")
    adapter_b = _MockAdapter("fw_b", "something unrelated")

    engine.run_benchmark(ResearchScenario(), [adapter_a, adapter_b], num_runs=2)

    leaderboard = engine.get_leaderboard()
    assert isinstance(leaderboard, list)
    assert len(leaderboard) == 2  # two frameworks

    for entry in leaderboard:
        assert "framework" in entry
        assert "scenario" in entry
        assert "avg_quality_score" in entry
        assert "avg_latency_ms" in entry
        assert "avg_token_cost" in entry
        assert "num_runs" in entry
        assert entry["num_runs"] == 2

    # Sorted descending by quality
    scores = [e["avg_quality_score"] for e in leaderboard]
    assert scores == sorted(scores, reverse=True)


# ── Test 10: BenchmarkEngine.get_recommendations returns best framework ───────

def test_get_recommendations_picks_best_framework():
    """get_recommendations should pick the highest-scoring framework per scenario."""
    engine = BenchmarkEngine()
    # fw_good responds with all keywords; fw_poor responds with nothing useful
    fw_good = _MockAdapter("fw_good", "attention encoder decoder transformer architecture")
    fw_poor = _MockAdapter("fw_poor", "lorem ipsum dolor sit amet")

    engine.run_benchmark(ResearchScenario(), [fw_good, fw_poor], num_runs=1)

    recommendations = engine.get_recommendations()
    assert "research" in recommendations
    assert recommendations["research"] == "fw_good"


def test_get_recommendations_empty_when_no_results():
    """With no benchmark runs, recommendations should be an empty dict."""
    engine = BenchmarkEngine()
    assert engine.get_recommendations() == {}


# ── Test 11: get_result by run_id ─────────────────────────────────────────────

def test_get_result_by_run_id():
    """get_result should return the matching record or None."""
    engine = BenchmarkEngine()
    adapter = _MockAdapter("fw_x", "Name,Score Alice 85 average 85")
    results = engine.run_benchmark(DataAnalysisScenario(), [adapter], num_runs=1)

    run_id = results[0]["run_id"]
    record = engine.get_result(run_id)
    assert record is not None
    assert record["run_id"] == run_id

    assert engine.get_result("nonexistent-id") is None


# ── Test 12: Multiple scenarios accumulate independently ──────────────────────

def test_multiple_scenarios_accumulate():
    """Running different scenarios should accumulate all results."""
    engine = BenchmarkEngine()
    adapter = _MockAdapter("fw_z", "def fibonacci return attention encoder decoder")

    engine.run_benchmark(CodegenScenario(), [adapter], num_runs=1)
    engine.run_benchmark(ResearchScenario(), [adapter], num_runs=1)

    all_results = engine.get_results()
    assert len(all_results) == 2
    scenarios = {r["scenario"] for r in all_results}
    assert "codegen" in scenarios
    assert "research" in scenarios

    leaderboard = engine.get_leaderboard()
    lb_scenarios = {e["scenario"] for e in leaderboard}
    assert "codegen" in lb_scenarios
    assert "research" in lb_scenarios
