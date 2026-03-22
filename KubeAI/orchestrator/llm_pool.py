"""LLMPool is the node-pool analogue: tracks available LLM backends and selects the right model per workload tier."""

from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass, field
from enum import Enum

# ── Supported provider catalog ─────────────────────────────────────────────────
# Each entry describes how to connect to a provider via LiteLLM.
# api_key_env: env var to read the key from automatically.
# model_prefix: LiteLLM model string prefix (e.g. "gemini/", "groq/").
# needs_base_url: True for self-hosted / custom endpoints.
# default_base_url: Default base URL for providers that need it.
# default_models: Suggested model IDs per tier (fast/capable/best).
SUPPORTED_PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "name": "Anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "required_env": ["ANTHROPIC_API_KEY"],
        "model_prefix": "",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "claude-haiku-4-5-20251001",
            "capable": "claude-sonnet-4-6",
            "best":    "claude-opus-4-6",
        },
    },
    "openai": {
        "name": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "required_env": ["OPENAI_API_KEY"],
        "model_prefix": "",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "gpt-4o-mini",
            "capable": "gpt-4o",
            "best":    "gpt-4o",
        },
    },
    "google": {
        "name": "Google Gemini",
        "api_key_env": "GEMINI_API_KEY",
        "required_env": ["GEMINI_API_KEY"],
        "model_prefix": "gemini/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "gemini/gemini-2.0-flash",
            "capable": "gemini/gemini-2.0-flash",
            "best":    "gemini/gemini-2.0-pro-exp",
        },
    },
    "groq": {
        "name": "Groq",
        "api_key_env": "GROQ_API_KEY",
        "required_env": ["GROQ_API_KEY"],
        "model_prefix": "groq/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "groq/llama-3.1-8b-instant",
            "capable": "groq/llama-3.3-70b-versatile",
            "best":    "groq/llama-3.3-70b-versatile",
        },
    },
    "mistral": {
        "name": "Mistral AI",
        "api_key_env": "MISTRAL_API_KEY",
        "required_env": ["MISTRAL_API_KEY"],
        "model_prefix": "mistral/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "mistral/mistral-small-latest",
            "capable": "mistral/mistral-large-latest",
            "best":    "mistral/mistral-large-latest",
        },
    },
    "cohere": {
        "name": "Cohere",
        "api_key_env": "COHERE_API_KEY",
        "required_env": ["COHERE_API_KEY"],
        "model_prefix": "cohere_chat/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "cohere_chat/command-r",
            "capable": "cohere_chat/command-r-plus",
            "best":    "cohere_chat/command-r-plus",
        },
    },
    "azure": {
        "name": "Azure OpenAI",
        "api_key_env": "AZURE_API_KEY",
        "required_env": ["AZURE_API_KEY", "AZURE_API_BASE"],
        "model_prefix": "azure/",
        "needs_base_url": True,
        "is_local": False,
        "default_models": {
            "fast":    "azure/gpt-4o-mini",
            "capable": "azure/gpt-4o",
            "best":    "azure/gpt-4o",
        },
    },
    "aws_bedrock": {
        "name": "AWS Bedrock",
        "api_key_env": "AWS_ACCESS_KEY_ID",
        "required_env": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION_NAME"],
        "model_prefix": "bedrock/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0",
            "capable": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
            "best":    "bedrock/anthropic.claude-3-opus-20240229-v1:0",
        },
    },
    "ollama": {
        "name": "Ollama (local)",
        "api_key_env": None,
        "required_env": [],
        "auto_detect": "endpoint",
        "model_prefix": "ollama/",
        "needs_base_url": True,
        "default_base_url": "http://localhost:11434",
        "is_local": True,
        "default_models": {
            "fast":    "ollama/llama3.2",
            "capable": "ollama/llama3.1",
            "best":    "ollama/llama3.1:70b",
        },
    },
    "openai_compatible": {
        "name": "OpenAI-compatible (vLLM / LM Studio / custom)",
        "api_key_env": "OPENAI_COMPATIBLE_API_KEY",
        "required_env": ["OPENAI_COMPATIBLE_API_KEY"],
        "auto_register": False,
        "model_prefix": "openai/",
        "needs_base_url": True,
        "default_base_url": "http://localhost:8000/v1",
        "is_local": True,
        "default_models": {
            "fast":    "openai/model",
            "capable": "openai/model",
            "best":    "openai/model",
        },
    },
    "deepseek": {
        "name": "Deepseek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "required_env": ["DEEPSEEK_API_KEY"],
        "model_prefix": "deepseek/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "deepseek/deepseek-chat",
            "capable": "deepseek/deepseek-chat",
            "best":    "deepseek/deepseek-reasoner",
        },
    },
    "together_ai": {
        "name": "Together AI",
        "api_key_env": "TOGETHERAI_API_KEY",
        "required_env": ["TOGETHERAI_API_KEY"],
        "model_prefix": "together_ai/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "together_ai/meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
            "capable": "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "best":    "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
        },
    },
    "fireworks_ai": {
        "name": "Fireworks AI",
        "api_key_env": "FIREWORKS_AI_API_KEY",
        "required_env": ["FIREWORKS_AI_API_KEY"],
        "model_prefix": "fireworks_ai/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "fireworks_ai/accounts/fireworks/models/llama-v3p2-11b-vision-instruct",
            "capable": "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct",
            "best":    "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct",
        },
    },
    "perplexity": {
        "name": "Perplexity",
        "api_key_env": "PERPLEXITYAI_API_KEY",
        "required_env": ["PERPLEXITYAI_API_KEY"],
        "model_prefix": "perplexity/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "perplexity/sonar",
            "capable": "perplexity/sonar-pro",
            "best":    "perplexity/sonar-pro",
        },
    },
    "xai": {
        "name": "xAI",
        "api_key_env": "XAI_API_KEY",
        "required_env": ["XAI_API_KEY"],
        "model_prefix": "xai/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "xai/grok-2-latest",
            "capable": "xai/grok-2-latest",
            "best":    "xai/grok-2-latest",
        },
    },
    "openrouter": {
        "name": "OpenRouter",
        "api_key_env": "OPENROUTER_API_KEY",
        "required_env": ["OPENROUTER_API_KEY"],
        "model_prefix": "openrouter/",
        "needs_base_url": False,
        "is_local": False,
        "default_models": {
            "fast":    "openrouter/meta-llama/llama-3.1-8b-instruct",
            "capable": "openrouter/anthropic/claude-sonnet-4",
            "best":    "openrouter/anthropic/claude-opus-4",
        },
    },
}


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

_TIER_FAST_HINTS = (
    "fast",
    "quick",
    "cheap",
    "small",
    "mini",
    "low latency",
)
_TIER_BEST_HINTS = (
    "best",
    "premium",
    "highest quality",
    "reasoning",
    "advanced",
    "max quality",
    "large",
    "70b",
)


def infer_model_tier(model_id: str, description: str) -> ModelTier:
    """Infer a model tier from free-text model metadata.

    This keeps registration UX description-first while preserving the tier-based
    scheduling contract required by blueprints.
    """
    text = f"{model_id} {description}".strip().lower()
    if not text:
        return ModelTier.CAPABLE

    if any(hint in text for hint in _TIER_BEST_HINTS):
        return ModelTier.BEST
    if any(hint in text for hint in _TIER_FAST_HINTS):
        return ModelTier.FAST
    return ModelTier.CAPABLE


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
    # Credentials — stored in memory only, never persisted to disk
    api_key: str = field(default="", repr=False)
    base_url: str = ""         # For Ollama, Azure, vLLM, custom endpoints

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
                    -relevance,
                    tier_distance,
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

    def start_health_probing(
        self, interval_s: float = 60.0, timeout_s: float = 10.0
    ) -> None:
        """Start background canary probing for all registered models (idempotent)."""
        from KubeAI.orchestrator.health_prober import HealthProber

        prober = HealthProber(self, interval_s=interval_s, timeout_s=timeout_s)
        prober.start()
        self._prober = prober

    def __repr__(self) -> str:
        with self._lock:
            return f"LLMPool(models={len(self._models)})"
