"""Codegen benchmark scenario — tests Python code generation quality."""

from __future__ import annotations

import re
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.benchmarks.scenarios.base import BenchmarkScenario


class CodegenScenario(BenchmarkScenario):
    """Benchmark scenario for code generation quality."""

    @property
    def name(self) -> str:
        return "codegen"

    def prepare(self) -> dict[str, Any]:
        return {
            "task": "Write a Python function that returns the nth Fibonacci number",
            "keywords": ["def", "fibonacci", "return"],
        }

    def execute(self, adapter: OrchestrationAdapter, setup: dict[str, Any]) -> AdapterResult:
        return adapter.invoke(
            task=setup["task"],
            system_prompt=(
                "You are an expert Python developer. Write clean, correct Python code. "
                "Include only the function definition and a brief docstring."
            ),
            model_id="claude-haiku-4-5-20251001",
        )

    def evaluate(self, result: AdapterResult, setup: dict[str, Any]) -> float:
        """Score by fraction of expected keywords present in the output."""
        keywords: list[str] = setup["keywords"]
        if not keywords:
            return 0.0
        output_lower = result.text.lower()
        matched = sum(1 for kw in keywords if kw.lower() in output_lower)
        return matched / len(keywords)
