"""RAG benchmark scenario — tests retrieval-augmented question answering."""

from __future__ import annotations

from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.benchmarks.scenarios.base import BenchmarkScenario
from KubeAI.benchmarks.scorer import score_output


class RagScenario(BenchmarkScenario):
    """Benchmark scenario for retrieval-augmented generation quality."""

    @property
    def name(self) -> str:
        return "rag"

    def prepare(self) -> dict[str, Any]:
        return {
            "question": "What is LlamaIndex used for?",
            "reference": (
                "LlamaIndex is used for building RAG pipelines and retrieval systems. "
                "It provides tools for indexing documents, querying vector stores, and "
                "connecting large language models to external data sources."
            ),
        }

    def execute(self, adapter: OrchestrationAdapter, setup: dict[str, Any]) -> AdapterResult:
        return adapter.invoke(
            task=setup["question"],
            system_prompt="Answer factually and concisely.",
            model_id="claude-haiku-4-5-20251001",
        )

    def evaluate(self, result: AdapterResult, setup: dict[str, Any]) -> float:
        return score_output(result.text, reference=setup["reference"])
