"""AdapterSelector — picks the best OrchestrationAdapter for a task type.

Queries benchmark leaderboard data (from BenchmarkEngine or PostgreSQL) and
returns the adapter with the highest weighted quality score for the given
scenario/task-type. Falls back to 'litellm' if no benchmark data exists.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from KubeAI.adapters.base import OrchestrationAdapter
from KubeAI.adapters.registry import AdapterRegistry

if TYPE_CHECKING:
    pass

# Task-type to scenario-name mapping
_TASK_TYPE_SCENARIOS: dict[str, str] = {
    "rag": "rag",
    "codegen": "codegen",
    "code": "codegen",
    "research": "research",
    "data_analysis": "data_analysis",
    "data": "data_analysis",
}

_DEFAULT_ADAPTER = "litellm"


class AdapterSelector:
    """Selects the best framework adapter for a given task type.

    Uses benchmark leaderboard data with recency-weighted scoring.
    Falls back to the litellm adapter when no benchmark data is available.

    Analogous to a Kubernetes scheduler plugin that scores nodes — each
    framework is a "node" and benchmark quality is the scoring signal.
    """

    def __init__(
        self,
        registry: AdapterRegistry,
        benchmark_engine: Any | None = None,
        recency_half_life_days: float = 7.0,
    ) -> None:
        """
        Args:
            registry: AdapterRegistry with all available framework adapters.
            benchmark_engine: Optional BenchmarkEngine instance for leaderboard data.
            recency_half_life_days: Benchmark scores decay with this half-life.
        """
        self._registry = registry
        self._benchmark_engine = benchmark_engine
        self._decay = recency_half_life_days

    def select(self, task_type: str) -> OrchestrationAdapter:
        """Return the best available adapter for the given task type.

        Args:
            task_type: One of 'rag', 'codegen', 'research', 'data_analysis',
                       or any alias defined in _TASK_TYPE_SCENARIOS.

        Returns:
            The adapter with the highest weighted benchmark score, or the
            default litellm adapter if no benchmark data is available.
        """
        scenario = _TASK_TYPE_SCENARIOS.get(task_type, task_type)
        scores = self._get_scores(scenario)

        # Filter to only registered + healthy adapters
        best_name = _DEFAULT_ADAPTER
        best_score = -1.0
        for framework, score in scores.items():
            if self._registry.has(framework):
                adapter = self._registry.get(framework)
                if adapter.health_check() and score > best_score:
                    best_score = score
                    best_name = framework

        # Fallback: use litellm if registered, else first healthy adapter
        if not self._registry.has(best_name):
            healthy = self._registry.healthy_adapters()
            if healthy:
                return healthy[0]
            raise RuntimeError("No healthy adapters available")

        return self._registry.get(best_name)

    def _get_scores(self, scenario: str) -> dict[str, float]:
        """Return weighted quality scores per framework for this scenario."""
        if self._benchmark_engine is None:
            return {}

        try:
            results = self._benchmark_engine.get_results()
        except (AttributeError, Exception):
            return {}

        now = datetime.now(tz=timezone.utc)
        framework_scores: dict[str, list[float]] = {}

        for r in results:
            if r.get("scenario") != scenario:
                continue
            framework = r.get("framework", "")
            quality = r.get("quality_score", 0.0)
            recorded_at_str = r.get("recorded_at", "")

            # Recency weighting: exponential decay
            weight = 1.0
            if recorded_at_str:
                try:
                    recorded_at = datetime.fromisoformat(recorded_at_str)
                    if recorded_at.tzinfo is None:
                        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
                    age_days = (now - recorded_at).total_seconds() / 86400
                    weight = math.exp(-math.log(2) * age_days / self._decay)
                except (ValueError, TypeError):
                    pass

            if framework not in framework_scores:
                framework_scores[framework] = []
            framework_scores[framework].append(quality * weight)

        return {fw: sum(scores) / len(scores) for fw, scores in framework_scores.items()}

    def recommend(self) -> dict[str, str]:
        """Return best framework name per scenario (for display/API)."""
        recommendations: dict[str, str] = {}
        for task_type, scenario in _TASK_TYPE_SCENARIOS.items():
            if scenario in recommendations:
                continue
            scores = self._get_scores(scenario)
            if not scores:
                recommendations[scenario] = _DEFAULT_ADAPTER
            else:
                best = max(scores, key=lambda k: scores[k])
                recommendations[scenario] = best
        return recommendations

    def __repr__(self) -> str:
        return (
            f"AdapterSelector(adapters={self._registry.list_names()}, "
            f"has_benchmark_data={self._benchmark_engine is not None})"
        )
