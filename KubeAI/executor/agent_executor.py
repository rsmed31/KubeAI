"""AgentExecutor is the kubelet analogue: runs a single task on a spawned agent via LiteLLM."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from KubeAI.adapters.base import OrchestrationAdapter
    from KubeAI.blueprint import Blueprint
    from KubeAI.memory.shared_memory import SharedMemory
    from KubeAI.orchestrator.assignment import Assignment
    from KubeAI.templates.base import Template


@dataclass
class AgentResult:
    """Outcome of a single agent task execution."""

    text: str
    latency_ms: float
    token_cost: float
    raw_usage: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"AgentResult(latency_ms={self.latency_ms:.1f}, "
            f"token_cost={self.token_cost:.6f}, "
            f"text_len={len(self.text)})"
        )


class AgentExecutor:
    """
    Executes a single task on a spawned agent using LiteLLM.

    Analogous to the Kubernetes kubelet: receives a pod spec (Blueprint +
    Assignment) and runs the workload. The ONLY place in KubeAI where LLM
    completion calls happen for task execution (routing uses Orchestrator).

    The executor is stateless — create one per process and reuse it.
    """

    # USD cost per 1k tokens used as fallback when the model pool has no entry
    _FALLBACK_COST_PER_1K = 0.002

    def run(
        self,
        task: str,
        blueprint: "Blueprint",
        assignment: "Assignment",
        memory: "SharedMemory | None" = None,
        agent_id: str | None = None,
        templates: "list[Template] | None" = None,
        adapter: "OrchestrationAdapter | None" = None,
    ) -> AgentResult:
        """
        Execute *task* using the model specified in *assignment*.

        Args:
            task: The user task description to execute.
            blueprint: The blueprint providing system_prompt and description.
            assignment: The spawn-time assignment selecting the model.
            memory: Optional SharedMemory for reading working context.
            agent_id: Optional agent ID used to load working-memory context.
            templates: Optional list of Template objects to attach for pre/post hooks.
                       Templates run pre_run() before LLM call and post_run() after.
            adapter: Optional OrchestrationAdapter. When provided, the adapter
                     handles the LLM call instead of the built-in _invoke_llm().

        Returns:
            AgentResult with generated text, latency, and token cost.

        Raises:
            RuntimeError: If the LiteLLM call fails.
        """
        try:
            import litellm  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "litellm is required for AgentExecutor. Install it with: pip install litellm"
            ) from exc

        system_content = blueprint.system_prompt or blueprint.description or "You are a helpful AI agent."

        # Load working-memory context if available
        context_lines: list[str] = []
        if memory is not None and agent_id is not None:
            for key in memory.keys_working(agent_id):
                value = memory.get_working(agent_id, key)
                if value is not None:
                    context_lines.append(f"[context:{key}] {value}")

        augmented_task = task
        if context_lines:
            augmented_task = "\n".join(context_lines) + "\n\n" + task

        # Apply template pre_run hooks (e.g. RAG context injection)
        if templates:
            from KubeAI.templates.base import attach_template, run_pre_hooks, run_post_hooks
            agent_obj = SimpleNamespace()
            for t in templates:
                try:
                    attach_template(agent_obj, t)
                except Exception:
                    pass  # Skip template failures — don't block execution
            augmented_task = run_pre_hooks(agent_obj, augmented_task)

        if adapter is not None:
            from KubeAI.adapters.base import AdapterResult as _AR
            adapter_result = adapter.invoke(
                task=augmented_task,
                system_prompt=system_content,
                model_id=assignment.model_id,
                api_key=assignment.api_key,
                base_url=assignment.base_url,
                max_tokens=2048,
            )
            result_text = adapter_result.text
            raw_usage = adapter_result.raw_usage
            latency_ms = adapter_result.latency_ms
        else:
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": augmented_task},
            ]

            t0 = time.monotonic()
            result_text, raw_usage = self._invoke_llm(
                litellm=litellm,
                messages=messages,
                assignment=assignment,
            )
            latency_ms = (time.monotonic() - t0) * 1000

        # Apply template post_run hooks
        if templates:
            from KubeAI.templates.base import run_post_hooks
            agent_obj_post = SimpleNamespace()
            for t in templates:
                try:
                    from KubeAI.templates.base import attach_template
                    attach_template(agent_obj_post, t)
                except Exception:
                    pass
            result_text = run_post_hooks(agent_obj_post, result_text)

        total_tokens = raw_usage.get("total_tokens", 0)
        token_cost = (total_tokens / 1000.0) * self._FALLBACK_COST_PER_1K

        return AgentResult(
            text=result_text,
            latency_ms=latency_ms,
            token_cost=token_cost,
            raw_usage=raw_usage,
        )

    def _invoke_llm(
        self,
        *,
        litellm: Any,
        messages: list[dict[str, str]],
        assignment: "Assignment",
    ) -> tuple[str, dict[str, Any]]:
        """
        Invoke the LLM using LangChain when available, falling back to direct
        LiteLLM. LangChain gives us tool calling, structured output, and
        LangGraph compatibility; direct LiteLLM is the zero-dependency path.

        Returns (result_text, raw_usage_dict).
        """
        # Build kwargs shared between LangChain and LiteLLM paths
        extra: dict[str, Any] = {}
        if assignment.api_key:
            extra["api_key"] = assignment.api_key
        if assignment.base_url:
            extra["api_base"] = assignment.base_url

        # ── LangChain path (preferred when installed) ──────────────────────
        try:
            from langchain_community.chat_models import ChatLiteLLM  # type: ignore[import]
            from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore[import]

            lc_messages = []
            for m in messages:
                if m["role"] == "system":
                    lc_messages.append(SystemMessage(content=m["content"]))
                else:
                    lc_messages.append(HumanMessage(content=m["content"]))

            chat = ChatLiteLLM(
                model=assignment.model_id,
                max_tokens=2048,
                **extra,
            )
            response = chat.invoke(lc_messages)
            text = response.content if hasattr(response, "content") else str(response)
            # LangChain usage metadata (available on AIMessage)
            usage_meta = getattr(response, "usage_metadata", None) or {}
            raw_usage: dict[str, Any] = {
                "prompt_tokens":     usage_meta.get("input_tokens", 0),
                "completion_tokens": usage_meta.get("output_tokens", 0),
                "total_tokens":      usage_meta.get("total_tokens", 0),
            }
            return text, raw_usage

        except ImportError:
            pass  # LangChain not installed — use direct LiteLLM below
        except Exception as exc:
            raise RuntimeError(
                f"LangChain invocation failed for model {assignment.model_id!r}: {exc}"
            ) from exc

        # ── Direct LiteLLM path (fallback) ────────────────────────────────
        try:
            response = litellm.completion(
                model=assignment.model_id,
                messages=messages,
                max_tokens=2048,
                **extra,
            )
        except Exception as exc:
            raise RuntimeError(
                f"LiteLLM completion failed for model {assignment.model_id!r}: {exc}"
            ) from exc

        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        raw_usage = {}
        if usage is not None:
            raw_usage = {
                "prompt_tokens":     getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens":      getattr(usage, "total_tokens", 0) or 0,
            }
        return text, raw_usage

    def __repr__(self) -> str:
        return "AgentExecutor()"
