"""Data analysis benchmark scenario — tests structured data interpretation quality."""

from __future__ import annotations

import re
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.benchmarks.scenarios.base import BenchmarkScenario


class DataAnalysisScenario(BenchmarkScenario):
    """Benchmark scenario for data analysis and numerical reasoning quality."""

    @property
    def name(self) -> str:
        return "data_analysis"

    def prepare(self) -> dict[str, Any]:
        return {
            "data": "Name,Score\nAlice,85\nBob,92\nCarol,78",
            "question": "What is the average score?",
        }

    def execute(self, adapter: OrchestrationAdapter, setup: dict[str, Any]) -> AdapterResult:
        task = (
            f"Given the following CSV data:\n{setup['data']}\n\n"
            f"Answer this question: {setup['question']}"
        )
        return adapter.invoke(
            task=task,
            system_prompt=(
                "You are a data analyst. Analyze the provided data and answer the question "
                "accurately. Show your calculation."
            ),
            model_id="claude-haiku-4-5-20251001",
        )

    def evaluate(self, result: AdapterResult, setup: dict[str, Any]) -> float:
        """Score by checking presence of 'average' keyword and a number near 85.

        The expected average is (85 + 92 + 78) / 3 = 85.0.
        We accept any number in the range [83.0, 87.0] to allow rounding variations.
        """
        output_lower = result.text.lower()

        has_average_word = "average" in output_lower or "mean" in output_lower

        # Extract all numeric values from the output
        numbers = re.findall(r"\d+\.?\d*", result.text)
        has_correct_number = any(83.0 <= float(n) <= 87.0 for n in numbers)

        if has_average_word and has_correct_number:
            return 1.0
        if has_average_word or has_correct_number:
            return 0.5
        return 0.0
