"""LlamaIndex adapter — wraps LlamaIndex for query-engine-style task execution."""

from __future__ import annotations

import time
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter


class LlamaIndexAdapter(OrchestrationAdapter):
    """Execute tasks via LlamaIndex with LiteLLM as the model backend.

    For tasks without documents, uses a simple LLM completion through LlamaIndex.
    For RAG-style tasks, integrates with LlamaIndex's query engine.
    """

    _FALLBACK_COST_PER_1K = 0.002

    @property
    def name(self) -> str:
        return "llamaindex"

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
        from llama_index.core.llms import ChatMessage, MessageRole
        from llama_index.llms.litellm import LiteLLM  # type: ignore[import]

        llm_kwargs: dict[str, Any] = {"model": model_id, "max_tokens": max_tokens}
        if api_key:
            llm_kwargs["api_key"] = api_key
        if base_url:
            llm_kwargs["api_base"] = base_url

        llm = LiteLLM(**llm_kwargs)

        messages = [ChatMessage(role=MessageRole.SYSTEM, content=system_prompt)]
        user_content = f"Context:\n{context}\n\nTask: {task}" if context else task
        messages.append(ChatMessage(role=MessageRole.USER, content=user_content))

        t0 = time.monotonic()
        response = llm.chat(messages)
        latency_ms = (time.monotonic() - t0) * 1000

        text = str(response.message.content) if response.message else ""
        raw_meta = getattr(response, "raw", None) or {}
        usage = raw_meta.get("usage", {}) if isinstance(raw_meta, dict) else {}
        raw_usage = {
            "prompt_tokens": (
                getattr(usage, "prompt_tokens", 0)
                if not isinstance(usage, dict)
                else usage.get("prompt_tokens", 0)
            ),
            "completion_tokens": (
                getattr(usage, "completion_tokens", 0)
                if not isinstance(usage, dict)
                else usage.get("completion_tokens", 0)
            ),
            "total_tokens": (
                getattr(usage, "total_tokens", 0)
                if not isinstance(usage, dict)
                else usage.get("total_tokens", 0)
            ),
        }
        total = raw_usage["total_tokens"]
        cost = (total / 1000.0) * self._FALLBACK_COST_PER_1K

        return AdapterResult(
            text=text,
            latency_ms=latency_ms,
            token_cost=cost,
            raw_usage=raw_usage,
            framework="llamaindex",
        )

    def health_check(self) -> bool:
        try:
            from llama_index.core.llms import ChatMessage  # noqa: F401
            from llama_index.llms.litellm import LiteLLM  # noqa: F401

            return True
        except ImportError:
            return False
