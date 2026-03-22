"""Tests for AdapterSelector — benchmark-informed framework selection."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.adapters.registry import AdapterRegistry
from KubeAI.adapters.selector import AdapterSelector


class _DummyAdapter(OrchestrationAdapter):
    def __init__(self, name: str, healthy: bool = True) -> None:
        self._name = name
        self._healthy = healthy

    @property
    def name(self) -> str:
        return self._name

    def invoke(self, *, task: str, system_prompt: str, model_id: str, **kwargs) -> AdapterResult:
        return AdapterResult(text="ok", latency_ms=10.0, token_cost=0.0, framework=self._name)

    def health_check(self) -> bool:
        return self._healthy


def _make_registry(*names: str) -> AdapterRegistry:
    reg = AdapterRegistry()
    for name in names:
        reg.register(_DummyAdapter(name))
    return reg


def test_selector_fallback_no_benchmark_data():
    reg = _make_registry("litellm", "langchain")
    selector = AdapterSelector(reg, benchmark_engine=None)
    adapter = selector.select("codegen")
    # Falls back to litellm (default) when no benchmark data
    assert adapter.name == "litellm"


def test_selector_uses_best_scored_adapter():
    reg = _make_registry("litellm", "langchain")

    # Mock benchmark engine with results
    engine = MagicMock()
    now = datetime.now(tz=timezone.utc).isoformat()
    engine.get_results.return_value = [
        {"scenario": "codegen", "framework": "litellm", "quality_score": 0.6, "recorded_at": now},
        {"scenario": "codegen", "framework": "langchain", "quality_score": 0.9, "recorded_at": now},
    ]
    selector = AdapterSelector(reg, benchmark_engine=engine)
    adapter = selector.select("codegen")
    assert adapter.name == "langchain"


def test_selector_skips_unhealthy_adapter():
    reg = AdapterRegistry()
    reg.register(_DummyAdapter("litellm", healthy=True))
    reg.register(_DummyAdapter("langchain", healthy=False))

    engine = MagicMock()
    now = datetime.now(tz=timezone.utc).isoformat()
    engine.get_results.return_value = [
        {"scenario": "rag", "framework": "langchain", "quality_score": 0.99, "recorded_at": now},
        {"scenario": "rag", "framework": "litellm", "quality_score": 0.5, "recorded_at": now},
    ]
    selector = AdapterSelector(reg, benchmark_engine=engine)
    adapter = selector.select("rag")
    # langchain has higher score but is unhealthy — should fall back to litellm
    assert adapter.name == "litellm"


def test_selector_task_type_alias():
    reg = _make_registry("litellm", "langchain")

    engine = MagicMock()
    now = datetime.now(tz=timezone.utc).isoformat()
    engine.get_results.return_value = [
        {"scenario": "codegen", "framework": "langchain", "quality_score": 0.8, "recorded_at": now},
    ]
    selector = AdapterSelector(reg, benchmark_engine=engine)
    # "code" is an alias for "codegen"
    adapter = selector.select("code")
    assert adapter.name == "langchain"


def test_selector_unknown_task_type_falls_back():
    reg = _make_registry("litellm")
    selector = AdapterSelector(reg, benchmark_engine=None)
    adapter = selector.select("unknown_task_type")
    assert adapter.name == "litellm"


def test_selector_recommend_all_scenarios():
    reg = _make_registry("litellm")
    selector = AdapterSelector(reg, benchmark_engine=None)
    recs = selector.recommend()
    assert "rag" in recs
    assert "codegen" in recs
    assert "research" in recs
    assert "data_analysis" in recs
    # All should fall back to litellm with no data
    for v in recs.values():
        assert v == "litellm"


def test_selector_repr():
    reg = _make_registry("litellm")
    selector = AdapterSelector(reg)
    assert "litellm" in repr(selector)


def test_selector_raises_if_no_adapters():
    reg = AdapterRegistry()  # empty
    selector = AdapterSelector(reg)
    with pytest.raises(RuntimeError, match="No healthy adapters"):
        selector.select("rag")
