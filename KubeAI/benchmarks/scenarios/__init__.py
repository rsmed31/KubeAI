"""Benchmark scenarios package."""

from KubeAI.benchmarks.scenarios.base import BenchmarkScenario
from KubeAI.benchmarks.scenarios.codegen_scenario import CodegenScenario
from KubeAI.benchmarks.scenarios.data_analysis_scenario import DataAnalysisScenario
from KubeAI.benchmarks.scenarios.rag_scenario import RagScenario
from KubeAI.benchmarks.scenarios.research_scenario import ResearchScenario

__all__ = [
    "BenchmarkScenario",
    "CodegenScenario",
    "DataAnalysisScenario",
    "RagScenario",
    "ResearchScenario",
]
