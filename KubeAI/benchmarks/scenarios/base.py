"""BenchmarkScenario — abstract base class for all benchmark scenarios."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter


class BenchmarkScenario(ABC):
    """Abstract base class for a benchmark scenario.

    Each scenario encapsulates:
    - prepare(): set up test data (no side effects, returns a setup dict)
    - execute(): run the scenario against a given adapter
    - evaluate(): score the result quality 0.0-1.0
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique scenario identifier (e.g. 'rag', 'codegen')."""

    @abstractmethod
    def prepare(self) -> dict[str, Any]:
        """Set up test data.

        Returns a setup dict that is passed unchanged to execute() and evaluate().
        Must be deterministic and free of external I/O.
        """

    @abstractmethod
    def execute(self, adapter: OrchestrationAdapter, setup: dict[str, Any]) -> AdapterResult:
        """Run the scenario against the given adapter.

        Args:
            adapter: The framework adapter to invoke.
            setup: The dict returned by prepare().

        Returns:
            An AdapterResult with at least .text populated.
        """

    @abstractmethod
    def evaluate(self, result: AdapterResult, setup: dict[str, Any]) -> float:
        """Score the result quality.

        Args:
            result: The AdapterResult returned by execute().
            setup: The dict returned by prepare().

        Returns:
            A float in [0.0, 1.0] where 1.0 is perfect quality.
        """
