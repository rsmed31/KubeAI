"""Research benchmark scenario — tests structured research output quality."""

from __future__ import annotations

from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.benchmarks.scenarios.base import BenchmarkScenario


class ResearchScenario(BenchmarkScenario):
    """Benchmark scenario for research and information synthesis quality."""

    @property
    def name(self) -> str:
        return "research"

    def prepare(self) -> dict[str, Any]:
        return {
            "topic": "transformer architecture",
            "sections": ["attention", "encoder", "decoder"],
        }

    def execute(self, adapter: OrchestrationAdapter, setup: dict[str, Any]) -> AdapterResult:
        topic = setup["topic"]
        sections = setup["sections"]
        task = (
            f"Write a structured research summary on the topic: {topic}. "
            f"Your summary must cover these sections: {', '.join(sections)}."
        )
        return adapter.invoke(
            task=task,
            system_prompt=(
                "You are a research specialist. Produce a concise, structured summary "
                "covering all requested sections."
            ),
            model_id="claude-haiku-4-5-20251001",
        )

    def evaluate(self, result: AdapterResult, setup: dict[str, Any]) -> float:
        """Score by fraction of expected section keywords mentioned in the output."""
        sections: list[str] = setup["sections"]
        if not sections:
            return 0.0
        output_lower = result.text.lower()
        mentioned = sum(1 for s in sections if s.lower() in output_lower)
        return mentioned / len(sections)
