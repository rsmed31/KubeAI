"""Unit tests for LLMPool: cost/tier selection, failover, and routing-model override."""

from __future__ import annotations

import pytest

from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

HAIKU = ModelEntry("claude-haiku-4", "anthropic", ModelTier.FAST, cost_per_1k_tokens=0.001)
SONNET = ModelEntry("claude-sonnet-4", "anthropic", ModelTier.CAPABLE, cost_per_1k_tokens=0.003)
OPUS = ModelEntry("claude-opus-4", "anthropic", ModelTier.BEST, cost_per_1k_tokens=0.015)


def _pool(*entries: ModelEntry) -> LLMPool:
    pool = LLMPool()
    for e in entries:
        pool.register(e)
    return pool


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_and_list(self) -> None:
        pool = _pool(HAIKU, SONNET)
        assert len(pool.list_models()) == 2

    def test_register_replaces_existing(self) -> None:
        pool = _pool(HAIKU)
        updated = ModelEntry("claude-haiku-4", "anthropic", ModelTier.FAST, cost_per_1k_tokens=0.002)
        pool.register(updated)
        models = pool.list_models()
        assert len(models) == 1
        assert models[0].cost_per_1k_tokens == 0.002

    def test_update_health_sets_flags(self) -> None:
        pool = _pool(HAIKU)
        pool.update_health("claude-haiku-4", healthy=False, load=0.9)
        m = pool.list_models()[0]
        assert not m.healthy
        assert m.load == pytest.approx(0.9)

    def test_update_health_unknown_model_raises(self) -> None:
        pool = _pool(HAIKU)
        with pytest.raises(KeyError):
            pool.update_health("unknown-model", healthy=False)

    def test_repr(self) -> None:
        pool = _pool(HAIKU, SONNET)
        assert "2" in repr(pool)


# ---------------------------------------------------------------------------
# routing_model — must always return the largest registered model
# ---------------------------------------------------------------------------


class TestRoutingModel:
    def test_returns_best_tier_when_all_healthy(self) -> None:
        pool = _pool(HAIKU, SONNET, OPUS)
        assert pool.routing_model().tier == ModelTier.BEST

    def test_skips_unhealthy_best_falls_back_to_capable(self) -> None:
        pool = _pool(HAIKU, SONNET, OPUS)
        pool.update_health("claude-opus-4", healthy=False)
        model = pool.routing_model()
        assert model.model_id == "claude-sonnet-4"

    def test_falls_back_to_unhealthy_when_only_option(self) -> None:
        """No healthy model available → still returns something (graceful degradation)."""
        pool = _pool(OPUS)
        pool.update_health("claude-opus-4", healthy=False)
        assert pool.routing_model().model_id == "claude-opus-4"

    def test_empty_pool_raises(self) -> None:
        with pytest.raises(RuntimeError):
            LLMPool().routing_model()


# ---------------------------------------------------------------------------
# select — cost/tier/load signals
# ---------------------------------------------------------------------------


class TestSelect:
    def test_low_cost_hint_prefers_fast(self) -> None:
        pool = _pool(HAIKU, SONNET, OPUS)
        assert pool.select(minimum_tier=ModelTier.FAST, cost_hint=0.1).tier == ModelTier.FAST

    def test_mid_cost_hint_prefers_capable(self) -> None:
        pool = _pool(HAIKU, SONNET, OPUS)
        assert pool.select(minimum_tier=ModelTier.FAST, cost_hint=0.5).tier == ModelTier.CAPABLE

    def test_high_cost_hint_prefers_best(self) -> None:
        pool = _pool(HAIKU, SONNET, OPUS)
        assert pool.select(minimum_tier=ModelTier.FAST, cost_hint=0.9).tier == ModelTier.BEST

    def test_minimum_tier_clamps_desired(self) -> None:
        """When blueprint minimum > cost-hint desired tier, minimum wins."""
        pool = _pool(HAIKU, SONNET, OPUS)
        model = pool.select(minimum_tier=ModelTier.BEST, cost_hint=0.0)
        assert model.tier == ModelTier.BEST

    def test_overloaded_model_deprioritised(self) -> None:
        pool = _pool(HAIKU, SONNET, OPUS)
        pool.update_health("claude-sonnet-4", healthy=True, load=0.95)
        # cost_hint=0.5 wants CAPABLE (sonnet) but it's overloaded
        model = pool.select(minimum_tier=ModelTier.FAST, cost_hint=0.5)
        assert model.model_id != "claude-sonnet-4"

    def test_unhealthy_model_skipped_when_healthy_available(self) -> None:
        pool = _pool(HAIKU, SONNET)
        pool.update_health("claude-sonnet-4", healthy=False)
        model = pool.select(minimum_tier=ModelTier.FAST, cost_hint=0.5)
        assert model.healthy

    def test_falls_back_to_unhealthy_when_no_healthy_eligible(self) -> None:
        """All eligible models unhealthy → still returns the best of the bad."""
        pool = _pool(HAIKU)
        pool.update_health("claude-haiku-4", healthy=False)
        model = pool.select(minimum_tier=ModelTier.FAST, cost_hint=0.5)
        assert model.model_id == "claude-haiku-4"

    def test_no_eligible_tier_raises(self) -> None:
        pool = _pool(HAIKU)  # only FAST registered
        with pytest.raises(RuntimeError, match="tier"):
            pool.select(minimum_tier=ModelTier.BEST, cost_hint=0.5)

    def test_empty_pool_raises(self) -> None:
        with pytest.raises(RuntimeError):
            LLMPool().select()

    def test_repr_on_entry(self) -> None:
        assert "claude-haiku-4" in repr(HAIKU)
        assert "fast" in repr(HAIKU)

    def test_task_description_prefers_matching_model(self) -> None:
        coding = ModelEntry(
            "code-model",
            "anthropic",
            ModelTier.CAPABLE,
            cost_per_1k_tokens=0.003,
            description="python coding debug stack traces",
        )
        writing = ModelEntry(
            "writing-model",
            "anthropic",
            ModelTier.CAPABLE,
            cost_per_1k_tokens=0.003,
            description="creative writing storytelling prose",
        )
        pool = _pool(coding, writing)

        model = pool.select(
            minimum_tier=ModelTier.CAPABLE,
            cost_hint=0.5,
            task="debug this python stack trace",
        )
        assert model.model_id == "code-model"

    def test_local_task_prefers_ollama_or_local_runtime(self) -> None:
        cloud = ModelEntry(
            "cloud-fast",
            "anthropic",
            ModelTier.FAST,
            cost_per_1k_tokens=0.001,
        )
        ollama = ModelEntry(
            "llama3.1:8b",
            "ollama",
            ModelTier.FAST,
            cost_per_1k_tokens=0.0,
            description="local ollama runtime",
        )
        pool = _pool(cloud, ollama)

        model = pool.select(
            minimum_tier=ModelTier.FAST,
            cost_hint=0.1,
            task="run this offline on local ollama",
        )
        assert model.model_id == "llama3.1:8b"
        assert model.is_local_runtime() is True
