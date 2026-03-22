"""LangChain adapter — wraps LangChain's ChatLiteLLM for task execution."""

from __future__ import annotations

import time
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter


class LangChainAdapter(OrchestrationAdapter):
    """Execute tasks via LangChain with LiteLLM as the model backend."""

    _FALLBACK_COST_PER_1K = 0.002

    @property
    def name(self) -> str:
        return "langchain"

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
        from langchain_community.chat_models import ChatLiteLLM
        from langchain_core.messages import HumanMessage, SystemMessage

        extra: dict[str, Any] = {}
        if api_key:
            extra["api_key"] = api_key
        if base_url:
            extra["api_base"] = base_url

        messages = [SystemMessage(content=system_prompt)]
        if context:
            messages.append(HumanMessage(content=f"Context:\n{context}\n\nTask: {task}"))
        else:
            messages.append(HumanMessage(content=task))

        chat = ChatLiteLLM(model=model_id, max_tokens=max_tokens, **extra)

        t0 = time.monotonic()
        response = chat.invoke(messages)
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.content if hasattr(response, "content") else str(response)
        usage_meta = getattr(response, "usage_metadata", None) or {}
        raw_usage = {
            "prompt_tokens": usage_meta.get("input_tokens", 0),
            "completion_tokens": usage_meta.get("output_tokens", 0),
            "total_tokens": usage_meta.get("total_tokens", 0),
        }
        total = raw_usage["total_tokens"]
        cost = (total / 1000.0) * self._FALLBACK_COST_PER_1K

        return AdapterResult(
            text=text,
            latency_ms=latency_ms,
            token_cost=cost,
            raw_usage=raw_usage,
            framework="langchain",
        )

    def health_check(self) -> bool:
        try:
            from langchain_community.chat_models import ChatLiteLLM  # noqa: F401
            from langchain_core.messages import HumanMessage  # noqa: F401

            return True
        except ImportError:
            return False
