"""LLMPool is the node-pool analogue: tracks available LLM backends and selects the right model per workload tier."""

from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass
from enum import Enum


class ModelTier(str, Enum):
    """Capability tier for LLM models, ordered from cheapest to most capable."""

    FAST = "fast"
    CAPABLE = "capable"
    BEST = "best"

    def __ge__(self, other: "ModelTier") -> bool:  # type: ignore[override]
        return _TIER_RANK[self] >= _TIER_RANK[other]

    def __gt__(self, other: "ModelTier") -> bool:  # type: ignore[override]
        return _TIER_RANK[self] > _TIER_RANK[other]

    def __le__(self, other: "ModelTier") -> bool:  # type: ignore[override]
        return _TIER_RANK[self] <= _TIER_RANK[other]

    def __lt__(self, other: "ModelTier") -> bool:  # type: ignore[override]
        return _TIER_RANK[self] < _TIER_RANK[other]


_TIER_RANK: dict[ModelTier, int] = {
    ModelTier.FAST: 0,
    ModelTier.CAPABLE: 1,
    ModelTier.BEST: 2,
}

_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
_LOCAL_PROVIDERS = frozenset({
    "ollama",
    "local",
    "llama.cpp",
    "llamacpp",
    "vllm",
    "lmstudio",
})


@dataclass
class ModelEntry:
    """Registry entry for a single LLM backend."""

    model_id: str
    provider: str
    tier: ModelTier
    cost_per_1k_tokens: float  # USD
    load: float = 0.0          # 0.0 = idle, 1.0 = saturated
    healthy: bool = True
    description: str = ""
    is_local: bool = False

    def is_local_runtime(self) -> bool:
        """Return True when this model runs on a local runtime (e.g. Ollama)."""
        return self.is_local or self.provider.lower() in _LOCAL_PROVIDERS

    def __repr__(self) -> str:
        return (
            f"ModelEntry(model_id={self.model_id!r}, provider={self.provider!r}, "
            f"tier={self.tier.value!r}, local={self.is_local_runtime()}, "
            f"load={self.load:.2f}, healthy={self.healthy})"
        )


class LLMPool:
    """
    Registry and selector for LLM models.

    Analogous to a Kubernetes node pool: tracks available backends, maps
    tiers to models, and selects the best fit given cost, load, and blueprint
    minimum-tier constraints.

    Hard rule: orchestrator routing always runs on the largest registered model.
    """

    _LOAD_THRESHOLD: float = 0.85

    def __init__(self) -> None:
        self._models: dict[str, ModelEntry] = {}
        self._lock = threading.RLock()

    def register(self, entry: ModelEntry) -> None:
        """Add or replace a model entry in the pool (stored as a defensive copy)."""
        with self._lock:
            self._models[entry.model_id] = copy.copy(entry)

    def update_health(
        self,
        model_id: str,
        *,
        healthy: bool,
        load: float | None = None,
    ) -> None:
        """Update health and optional load for a registered model."""
        with self._lock:
            entry = self._models.get(model_id)
            if entry is None:
                raise KeyError(f"Model {model_id!r} not registered")
            entry.healthy = healthy
            if load is not None:
                entry.load = load

    def routing_model(self) -> ModelEntry:
        """
        Return the largest registered model for orchestrator routing decisions.

        Prefers healthy models but falls back to any model if all are unhealthy,
        degrading gracefully to the highest available tier.
        """
        with self._lock:
            if not self._models:
                raise RuntimeError("LLMPool has no registered models")

            candidates = sorted(
                self._models.values(),
                key=lambda m: (_TIER_RANK[m.tier], -m.load),
                reverse=True,
            )
            healthy = [m for m in candidates if m.healthy]
            return (healthy or candidates)[0]

    def select(
        self,
        *,
        minimum_tier: ModelTier = ModelTier.FAST,
        cost_hint: float = 0.5,
        task: str = "",
    ) -> ModelEntry:
        """
        Select a model for an agent workload.

        Args:
            minimum_tier: The lowest acceptable tier from the blueprint definition.
            cost_hint: Float 0.0-1.0 where 0.0 prefers cheapest and 1.0 prefers
                       highest capability regardless of cost.

        Returns:
            Best available ModelEntry after applying tier, cost, and load signals.

        Raises:
            RuntimeError: If no model satisfies the minimum tier constraint or
                          the pool is empty.
        """
        with self._lock:
            if not self._models:
                raise RuntimeError("LLMPool has no registered models")

            desired_tier = self._desired_tier(cost_hint)
            # Clamp to blueprint minimum — never go below what blueprint requires
            if _TIER_RANK[desired_tier] < _TIER_RANK[minimum_tier]:
                desired_tier = minimum_tier

            eligible = [
                m for m in self._models.values()
                if _TIER_RANK[m.tier] >= _TIER_RANK[minimum_tier]
            ]
            if not eligible:
                raise RuntimeError(
                    f"No models registered at or above tier {minimum_tier.value!r}"
                )

            prefer_local = self._prefers_local_runtime(task)

            def _score(m: ModelEntry) -> tuple[int, int, int, float, float]:
                # Lower score = more preferred
                tier_distance = abs(_TIER_RANK[m.tier] - _TIER_RANK[desired_tier])
                is_overloaded = int(m.load > self._LOAD_THRESHOLD)
                local_miss = int(prefer_local and not m.is_local_runtime())
                relevance = self._text_overlap(
                    task,
                    f"{m.model_id} {m.provider} {m.description}",
                )
                return (
                    is_overloaded,
                    local_miss,
                    tier_distance,
                    -relevance,
                    m.cost_per_1k_tokens,
                )

            healthy = [m for m in eligible if m.healthy]
            ranked = sorted(healthy or eligible, key=_score)
            return ranked[0]

    @staticmethod
    def _desired_tier(cost_hint: float) -> ModelTier:
        """Map a cost hint scalar to the preferred model tier."""
        if cost_hint < 0.33:
            return ModelTier.FAST
        if cost_hint < 0.67:
            return ModelTier.CAPABLE
        return ModelTier.BEST

    @staticmethod
    def _prefers_local_runtime(task: str) -> bool:
        lowered = task.lower()
        local_signals = (
            "local",
            "offline",
            "on-device",
            "on prem",
            "on-prem",
            "ollama",
        )
        return any(signal in lowered for signal in local_signals)

    @staticmethod
    def _text_overlap(task: str, description: str) -> float:
        if not task.strip() or not description.strip():
            return 0.0

        task_tokens = set(_TOKEN_PATTERN.findall(task.lower()))
        desc_tokens = set(_TOKEN_PATTERN.findall(description.lower()))
        if not task_tokens or not desc_tokens:
            return 0.0

        return float(len(task_tokens.intersection(desc_tokens)))

    def list_models(self) -> list[ModelEntry]:
        """Return a snapshot of all registered models."""
        with self._lock:
            return list(self._models.values())

    def __repr__(self) -> str:
        with self._lock:
            return f"LLMPool(models={len(self._models)})"
