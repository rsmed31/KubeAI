"""AutoGen adapter — wraps Microsoft AutoGen for task execution."""

from __future__ import annotations

import time
from typing import Any

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter


class AutoGenAdapter(OrchestrationAdapter):
    """Execute tasks via AutoGen with LiteLLM as the model backend.

    Uses a simple AssistantAgent + UserProxyAgent pair for single-turn
    task execution. Multi-turn conversations are supported but default
    to a single exchange for benchmark fairness.
    """

    _FALLBACK_COST_PER_1K = 0.002

    @property
    def name(self) -> str:
        return "autogen"

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
        import autogen  # type: ignore[import]

        # Configure LiteLLM model through AutoGen's config
        config_list = [
            {
                "model": model_id,
                "api_key": api_key or "not-needed",
            }
        ]
        if base_url:
            config_list[0]["base_url"] = base_url

        llm_config = {
            "config_list": config_list,
            "max_tokens": max_tokens,
            "temperature": 0,
        }

        assistant = autogen.AssistantAgent(
            name="assistant",
            system_message=system_prompt,
            llm_config=llm_config,
        )

        user_proxy = autogen.UserProxyAgent(
            name="user",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0,
            code_execution_config=False,
        )

        user_content = f"Context:\n{context}\n\nTask: {task}" if context else task

        t0 = time.monotonic()
        user_proxy.initiate_chat(assistant, message=user_content, silent=True)
        latency_ms = (time.monotonic() - t0) * 1000

        # Extract last assistant message
        chat_history = assistant.chat_messages.get(user_proxy, [])
        text = ""
        for msg in reversed(chat_history):
            if msg.get("role") == "assistant" and msg.get("content"):
                text = msg["content"]
                break

        # AutoGen doesn't expose token usage directly, estimate
        raw_usage: dict[str, Any] = {}
        total_tokens = 0
        try:
            usage_summary = assistant.get_total_usage()
            if usage_summary:
                total_tokens = usage_summary.get("total_tokens", 0)
                raw_usage = dict(usage_summary)
        except Exception:
            pass

        cost = (total_tokens / 1000.0) * self._FALLBACK_COST_PER_1K

        return AdapterResult(
            text=text,
            latency_ms=latency_ms,
            token_cost=cost,
            raw_usage=raw_usage,
            framework="autogen",
        )

    def health_check(self) -> bool:
        try:
            import autogen  # noqa: F401

            return True
        except ImportError:
            return False
