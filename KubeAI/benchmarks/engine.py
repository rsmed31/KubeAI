"""BenchmarkEngine — runs scenarios against adapters and aggregates results."""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from KubeAI.adapters.base import OrchestrationAdapter
from KubeAI.benchmarks.scenarios.base import BenchmarkScenario


class BenchmarkEngine:
    """Runs benchmark scenarios against framework adapters and stores results in memory.

    Analogous to a Kubernetes conformance test runner — exercises each adapter
    through standardised scenarios and produces a leaderboard and recommendations.

    Results are stored in-process (list of dicts). No external storage required.
    """

    def __init__(self) -> None:
        self._results: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_benchmark(
        self,
        scenario: BenchmarkScenario,
        adapters: list[OrchestrationAdapter],
        num_runs: int = 3,
    ) -> list[dict[str, Any]]:
        """Run *scenario* against each adapter *num_runs* times.

        For each (adapter, run) pair:
        1. Call scenario.prepare() to get a fresh setup dict.
        2. Call scenario.execute(adapter, setup) to get an AdapterResult.
        3. Call scenario.evaluate(result, setup) to get a quality score.
        4. Record the result dict and append it to the in-memory store.

        Args:
            scenario: The scenario to run.
            adapters: List of adapters to benchmark against each other.
            num_runs: Number of times to run each adapter (results are averaged
                      in get_leaderboard, but individual runs are stored).

        Returns:
            List of result dicts for this benchmark call only.
        """
        new_results: list[dict[str, Any]] = []

        for adapter in adapters:
            for _ in range(num_runs):
                setup = scenario.prepare()
                try:
                    result = scenario.execute(adapter, setup)
                    quality_score = scenario.evaluate(result, setup)
                    output_text = result.text
                    latency_ms = result.latency_ms
                    token_cost = result.token_cost
                except Exception as exc:
                    # Record failed run with zero scores so leaderboard stays consistent
                    quality_score = 0.0
                    output_text = f"[ERROR] {exc}"
                    latency_ms = 0.0
                    token_cost = 0.0

                record: dict[str, Any] = {
                    "run_id": str(uuid.uuid4()),
                    "scenario": scenario.name,
                    "framework": adapter.name,
                    "quality_score": float(quality_score),
                    "latency_ms": float(latency_ms),
                    "token_cost": float(token_cost),
                    "output_text": output_text,
                    "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
                }
                new_results.append(record)

        with self._lock:
            self._results.extend(new_results)

        return new_results

    def get_results(self) -> list[dict[str, Any]]:
        """Return a copy of all stored result records."""
        with self._lock:
            return list(self._results)

    def get_result(self, run_id: str) -> dict[str, Any] | None:
        """Return a single result record by run_id, or None if not found."""
        with self._lock:
            for record in self._results:
                if record["run_id"] == run_id:
                    return dict(record)
        return None

    def get_leaderboard(self) -> list[dict[str, Any]]:
        """Return aggregated scores per (framework, scenario) pair.

        Each entry contains:
        - framework: str
        - scenario: str
        - avg_quality_score: float
        - avg_latency_ms: float
        - avg_token_cost: float
        - num_runs: int

        Sorted by avg_quality_score descending.
        """
        with self._lock:
            records = list(self._results)

        # Group by (framework, scenario)
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in records:
            key = (r["framework"], r["scenario"])
            groups[key].append(r)

        leaderboard: list[dict[str, Any]] = []
        for (framework, scenario), runs in groups.items():
            n = len(runs)
            avg_quality = sum(r["quality_score"] for r in runs) / n
            avg_latency = sum(r["latency_ms"] for r in runs) / n
            avg_cost = sum(r["token_cost"] for r in runs) / n
            leaderboard.append({
                "framework": framework,
                "scenario": scenario,
                "avg_quality_score": round(avg_quality, 4),
                "avg_latency_ms": round(avg_latency, 2),
                "avg_token_cost": round(avg_cost, 6),
                "num_runs": n,
            })

        leaderboard.sort(key=lambda x: -x["avg_quality_score"])
        return leaderboard

    def get_recommendations(self) -> dict[str, str]:
        """Return the best framework per scenario type.

        For each scenario, pick the framework with the highest average quality score.

        Returns:
            Dict mapping scenario name -> best framework name.
            Empty dict if no results have been recorded yet.
        """
        leaderboard = self.get_leaderboard()

        # Per scenario: highest avg_quality_score wins
        best: dict[str, tuple[str, float]] = {}  # scenario -> (framework, score)
        for entry in leaderboard:
            scenario = entry["scenario"]
            framework = entry["framework"]
            score = entry["avg_quality_score"]
            if scenario not in best or score > best[scenario][1]:
                best[scenario] = (framework, score)

        return {scenario: fw for scenario, (fw, _) in best.items()}
