"""OrchestrationAdapter — abstract interface wrapping any AI agent framework."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterResult:
    """Standardized result from any framework adapter."""
    text: str
    latency_ms: float
    token_cost: float
    raw_usage: dict[str, Any] = field(default_factory=dict)
    framework: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class OrchestrationAdapter(ABC):
    """Abstract interface wrapping any AI agent framework.

    All adapters return AdapterResult so the runtime can swap frameworks
    via config without changing execution logic.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Framework identifier (e.g. 'langchain', 'litellm')."""

    @abstractmethod
    def invoke(
        self,
        *,
        task: str,
        system_prompt: str,
        model_id: str,
        api_key: str = "",
        base_url: str = "",
        max_tokens: int = 2048,
        tools: list[dict] | None = None,
        context: str = "",
        **kwargs: Any,
    ) -> AdapterResult:
        """Execute a task through this framework and return standardized results."""

    def health_check(self) -> bool:
        """Return True if this adapter's dependencies are available."""
        return True
