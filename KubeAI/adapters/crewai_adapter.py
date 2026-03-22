"""CrewAI adapter — wraps CrewAI for task execution."""

from __future__ import annotations

import time
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter


class CrewAIAdapter(OrchestrationAdapter):
    """Execute tasks via CrewAI with LiteLLM as the model backend.

    Uses a single-agent Crew for fair benchmark comparison.
    """

    _FALLBACK_COST_PER_1K = 0.002

    @property
    def name(self) -> str:
        return "crewai"

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
        from crewai import Agent, Crew, Task  # type: ignore[import]

        # CrewAI uses LiteLLM under the hood for model routing
        agent = Agent(
            role="AI Agent",
            goal=system_prompt,
            backstory=system_prompt,
            llm=model_id,
            verbose=False,
            allow_delegation=False,
        )

        user_content = f"Context:\n{context}\n\nTask: {task}" if context else task

        crew_task = Task(
            description=user_content,
            expected_output="A clear, complete response to the task.",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[crew_task],
            verbose=False,
        )

        t0 = time.monotonic()
        result = crew.kickoff()
        latency_ms = (time.monotonic() - t0) * 1000

        text = str(result) if result else ""
        raw_usage: dict[str, Any] = {}

        # Try to extract token usage from CrewAI result
        try:
            usage_metrics = getattr(result, "token_usage", None)
            if usage_metrics:
                raw_usage = {
                    "prompt_tokens": getattr(usage_metrics, "prompt_tokens", 0),
                    "completion_tokens": getattr(
                        usage_metrics, "completion_tokens", 0
                    ),
                    "total_tokens": getattr(usage_metrics, "total_tokens", 0),
                }
        except Exception:
            pass

        total = raw_usage.get("total_tokens", 0)
        cost = (total / 1000.0) * self._FALLBACK_COST_PER_1K

        return AdapterResult(
            text=text,
            latency_ms=latency_ms,
            token_cost=cost,
            raw_usage=raw_usage,
            framework="crewai",
        )

    def health_check(self) -> bool:
        try:
            from crewai import Agent, Crew, Task  # noqa: F401

            return True
        except ImportError:
            return False
