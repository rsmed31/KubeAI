"""LiteLLM adapter — wraps the existing dual LangChain/LiteLLM execution path."""

from __future__ import annotations

import time
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter


class LiteLLMAdapter(OrchestrationAdapter):
    """Native LiteLLM adapter using the existing dual-path invocation.

    Tries LangChain's ChatLiteLLM when available, falls back to direct
    litellm.completion(). This preserves the exact behavior of the
    original AgentExecutor._invoke_llm() method.
    """

    _FALLBACK_COST_PER_1K = 0.002

    @property
    def name(self) -> str:
        return "litellm"

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
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("litellm is required") from exc

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        extra: dict[str, Any] = {}
        if api_key:
            extra["api_key"] = api_key
        if base_url:
            extra["api_base"] = base_url

        t0 = time.monotonic()
        text, raw_usage = self._call(litellm, messages, model_id, max_tokens, extra)
        latency_ms = (time.monotonic() - t0) * 1000

        total_tokens = raw_usage.get("total_tokens", 0)
        token_cost = (total_tokens / 1000.0) * self._FALLBACK_COST_PER_1K

        return AdapterResult(
            text=text,
            latency_ms=latency_ms,
            token_cost=token_cost,
            raw_usage=raw_usage,
            framework="litellm",
        )

    def _call(
        self,
        litellm: Any,
        messages: list[dict],
        model_id: str,
        max_tokens: int,
        extra: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Try LangChain path first, fall back to direct LiteLLM."""
        # LangChain path
        try:
            from langchain_community.chat_models import ChatLiteLLM
            from langchain_core.messages import HumanMessage, SystemMessage

            lc_messages = []
            for m in messages:
                if m["role"] == "system":
                    lc_messages.append(SystemMessage(content=m["content"]))
                else:
                    lc_messages.append(HumanMessage(content=m["content"]))

            chat = ChatLiteLLM(model=model_id, max_tokens=max_tokens, **extra)
            response = chat.invoke(lc_messages)
            text = response.content if hasattr(response, "content") else str(response)
            usage_meta = getattr(response, "usage_metadata", None) or {}
            raw_usage = {
                "prompt_tokens": usage_meta.get("input_tokens", 0),
                "completion_tokens": usage_meta.get("output_tokens", 0),
                "total_tokens": usage_meta.get("total_tokens", 0),
            }
            return text, raw_usage
        except ImportError:
            pass
        except Exception as exc:
            raise RuntimeError(f"LangChain invocation failed for {model_id!r}: {exc}") from exc

        # Direct LiteLLM path
        try:
            response = litellm.completion(
                model=model_id, messages=messages, max_tokens=max_tokens, **extra,
            )
        except Exception as exc:
            raise RuntimeError(f"LiteLLM completion failed for {model_id!r}: {exc}") from exc

        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        raw_usage = {}
        if usage is not None:
            raw_usage = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            }
        return text, raw_usage

    def health_check(self) -> bool:
        try:
            import litellm  # noqa: F401
            return True
        except ImportError:
            return False
