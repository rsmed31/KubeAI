"""Integration tests — full adapter selection and invocation pipeline.

These tests exercise the AdapterRegistry + LiteLLMAdapter + AdapterSelector
pipeline end-to-end. All HTTP calls are intercepted by respx so no real API
keys are needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.adapters.litellm_adapter import LiteLLMAdapter
from KubeAI.adapters.registry import AdapterRegistry
from KubeAI.adapters.selector import AdapterSelector


class _DummyAdapter(OrchestrationAdapter):
    """Deterministic adapter used in selection tests — never makes HTTP calls."""

    def __init__(self, adapter_name: str, score_hint: float = 0.5) -> None:
        self._adapter_name = adapter_name
        self.score_hint = score_hint

    @property
    def name(self) -> str:
        return self._adapter_name

    def invoke(
        self,
        *,
        task: str,
        system_prompt: str,
        model_id: str,
        **kwargs,
    ) -> AdapterResult:
        return AdapterResult(
            text=f"{self._adapter_name}:{task}",
            latency_ms=5.0,
            token_cost=0.001,
            framework=self._adapter_name,
        )


# ---------------------------------------------------------------------------
# Test 1: Register LiteLLMAdapter, invoke it with mocked HTTP
# ---------------------------------------------------------------------------

def test_litellm_adapter_invoke_with_mocked_http():
    """LiteLLMAdapter.invoke() returns a populated AdapterResult with mocked call path."""
    adapter = LiteLLMAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    assert registry.has("litellm")

    with patch.object(
        LiteLLMAdapter,
        "_call",
        return_value=(
            "Hello from mock",
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        ),
    ):
        result = adapter.invoke(
            task="Say hello",
            system_prompt="You are a helpful assistant.",
            model_id="claude-haiku-4-5-20251001",
            api_key="sk-fake-key",
        )

    assert isinstance(result, AdapterResult)
    assert isinstance(result.text, str)
    assert len(result.text) > 0
    assert result.framework == "litellm"
    assert result.latency_ms >= 0.0
    assert result.token_cost >= 0.0


# ---------------------------------------------------------------------------
# Test 2: AdapterSelector falls back to litellm when there is no benchmark data
# ---------------------------------------------------------------------------

def test_adapter_selector_returns_litellm_when_no_benchmark_data():
    """With benchmark_engine=None, select() always returns the litellm adapter."""
    registry = AdapterRegistry()
    registry.register(_DummyAdapter("litellm"))
    registry.register(_DummyAdapter("langchain"))

    selector = AdapterSelector(registry, benchmark_engine=None)
    adapter = selector.select("rag")

    assert adapter.name == "litellm"


# ---------------------------------------------------------------------------
# Test 3: AdapterSelector picks the best adapter based on injected scores
# ---------------------------------------------------------------------------

def test_adapter_selector_picks_best_from_benchmark_scores():
    """select() returns the adapter with the highest benchmark quality score."""
    registry = AdapterRegistry()
    registry.register(_DummyAdapter("litellm"))
    registry.register(_DummyAdapter("langchain"))

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    engine = MagicMock()
    engine.get_results.return_value = [
        {"scenario": "codegen", "framework": "litellm",  "quality_score": 0.55, "recorded_at": now_iso},
        {"scenario": "codegen", "framework": "langchain", "quality_score": 0.88, "recorded_at": now_iso},
    ]

    selector = AdapterSelector(registry, benchmark_engine=engine)
    adapter = selector.select("codegen")

    assert adapter.name == "langchain"


# ---------------------------------------------------------------------------
# Test 4: AdapterResult has all expected fields after invocation
# ---------------------------------------------------------------------------

def test_adapter_result_has_all_expected_fields():
    """AdapterResult from a DummyAdapter has every field populated correctly."""
    adapter = _DummyAdapter("test_fw")
    result = adapter.invoke(
        task="explain transformers",
        system_prompt="Be brief.",
        model_id="any-model",
    )

    assert isinstance(result.text, str)
    assert "test_fw" in result.text
    assert isinstance(result.latency_ms, float)
    assert result.latency_ms >= 0.0
    assert isinstance(result.token_cost, float)
    assert result.token_cost >= 0.0
    assert result.framework == "test_fw"
    assert isinstance(result.raw_usage, dict)
    assert isinstance(result.metadata, dict)


# ---------------------------------------------------------------------------
# Test 5: AdapterRegistry correctly stores and retrieves the adapter
# ---------------------------------------------------------------------------

def test_adapter_registry_register_and_retrieve():
    """Registering an adapter and then fetching it returns the exact same object."""
    registry = AdapterRegistry()
    adapter = _DummyAdapter("my_adapter")
    registry.register(adapter)

    assert registry.has("my_adapter")
    assert registry.get("my_adapter") is adapter
    assert "my_adapter" in registry.list_names()
    assert len(registry) == 1


# ---------------------------------------------------------------------------
# Test 6: AdapterSelector ignores adapters that are not in the registry
# ---------------------------------------------------------------------------

def test_adapter_selector_ignores_scores_for_unregistered_adapters():
    """Scores for unregistered frameworks are ignored; litellm is the fallback."""
    registry = AdapterRegistry()
    registry.register(_DummyAdapter("litellm"))
    # "superfw" is NOT registered

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    engine = MagicMock()
    engine.get_results.return_value = [
        {"scenario": "research", "framework": "superfw", "quality_score": 0.99, "recorded_at": now_iso},
        {"scenario": "research", "framework": "litellm",  "quality_score": 0.40, "recorded_at": now_iso},
    ]

    selector = AdapterSelector(registry, benchmark_engine=engine)
    adapter = selector.select("research")

    # superfw not in registry, so litellm wins by being the only healthy option
    assert adapter.name == "litellm"
