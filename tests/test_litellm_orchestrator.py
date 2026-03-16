"""Tests for LiteLLM-backed orchestrator functions (_llm_score, _llm_decompose, Orchestrator.route)."""

from __future__ import annotations

import sys
import types

import pytest

from KubeAI.blueprint import Blueprint
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool
from KubeAI.orchestrator.orchestrator import Orchestrator, _llm_decompose, _llm_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy() -> AssignmentPolicy:
    pool = LLMPool()
    pool.register(
        ModelEntry(
            model_id="model-fast",
            provider="test",
            tier=ModelTier.FAST,
            cost_per_1k_tokens=0.01,
        )
    )
    return AssignmentPolicy(pool, MCPPool())


def _make_blueprint(name: str = "bp") -> Blueprint:
    return Blueprint(
        name=name,
        description=f"Test blueprint: {name}",
        tier=ModelTier.FAST,
    )


def _stub_litellm_raise() -> types.ModuleType:
    """Return a fake litellm module whose completion() always raises."""
    mod = types.ModuleType("litellm")

    def _raise(*args: object, **kwargs: object) -> object:
        raise RuntimeError("simulated litellm failure")

    mod.completion = _raise  # type: ignore[attr-defined]
    return mod


# ---------------------------------------------------------------------------
# _llm_score tests
# ---------------------------------------------------------------------------


def test_llm_score_returns_zero_when_litellm_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """_llm_score must return 0.0 whenever litellm.completion raises."""
    monkeypatch.setitem(sys.modules, "litellm", _stub_litellm_raise())
    bp = _make_blueprint()
    result = _llm_score("some task", bp, "model-fast")
    assert result == 0.0


def test_llm_score_returns_zero_when_litellm_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """_llm_score must return 0.0 when litellm is not installed (ImportError path)."""
    # Remove litellm from sys.modules so the try/except ImportError triggers
    monkeypatch.setitem(sys.modules, "litellm", None)  # type: ignore[arg-type]
    bp = _make_blueprint()
    result = _llm_score("some task", bp, "model-fast")
    assert result == 0.0


# ---------------------------------------------------------------------------
# _llm_decompose tests
# ---------------------------------------------------------------------------


def test_llm_decompose_returns_task_list_when_litellm_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_llm_decompose must return [task] whenever litellm.completion raises."""
    monkeypatch.setitem(sys.modules, "litellm", _stub_litellm_raise())
    task = "a complex research task"
    result = _llm_decompose(task, "model-fast")
    assert result == [task]


def test_llm_decompose_returns_task_list_when_litellm_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_llm_decompose must return [task] when litellm is not installed."""
    monkeypatch.setitem(sys.modules, "litellm", None)  # type: ignore[arg-type]
    task = "another task"
    result = _llm_decompose(task, "model-fast")
    assert result == [task]


# ---------------------------------------------------------------------------
# Orchestrator.route with missing litellm
# ---------------------------------------------------------------------------


def test_orchestrator_route_does_not_crash_when_litellm_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestrator.route must not raise even when litellm is unavailable."""
    monkeypatch.setitem(sys.modules, "litellm", None)  # type: ignore[arg-type]
    policy = _make_policy()
    orch = Orchestrator(policy)
    bp = _make_blueprint("research")
    # _llm_score will return 0.0 for all blueprints — route still picks one
    result_bp, score = orch.route("summarise a paper", [bp])
    assert result_bp.name == "research"
    assert score == 0.0


def test_orchestrator_route_does_not_crash_when_litellm_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestrator.route must not raise even when litellm.completion raises."""
    monkeypatch.setitem(sys.modules, "litellm", _stub_litellm_raise())
    policy = _make_policy()
    orch = Orchestrator(policy)
    bp1 = _make_blueprint("coder")
    bp2 = _make_blueprint("writer")
    result_bp, score = orch.route("write some code", [bp1, bp2])
    # Both scored 0.0 → first by stable sort wins; either is valid
    assert result_bp.name in {"coder", "writer"}
    assert score == 0.0


# ---------------------------------------------------------------------------
# Orchestrator.route with injected score_fn (no real LLM)
# ---------------------------------------------------------------------------


def test_orchestrator_route_uses_injected_score_fn() -> None:
    """Orchestrator.route must use the injected score_fn, not the default LiteLLM scorer."""
    policy = _make_policy()
    scores = {"alpha": 0.9, "beta": 0.3}
    score_fn = lambda task, bp, model_id: scores.get(bp.name, 0.0)  # noqa: E731
    orch = Orchestrator(policy, score_fn=score_fn)
    blueprints = [_make_blueprint("alpha"), _make_blueprint("beta")]
    best, confidence = orch.route("anything", blueprints)
    assert best.name == "alpha"
    assert confidence == pytest.approx(0.9)


def test_orchestrator_route_returns_single_blueprint_regardless_of_score() -> None:
    """Orchestrator.route must return the only blueprint even when score is 0.0."""
    policy = _make_policy()
    orch = Orchestrator(policy, score_fn=lambda t, bp, m: 0.0)
    bp = _make_blueprint("only-one")
    result_bp, score = orch.route("task", [bp])
    assert result_bp.name == "only-one"
    assert score == 0.0
