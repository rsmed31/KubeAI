"""AgentExecutor is the kubelet analogue: runs a single task on a spawned agent via LiteLLM."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": augmented_task},
        ]

        t0 = time.monotonic()
        try:
            response = litellm.completion(
                model=assignment.model_id,
                messages=messages,
                max_tokens=2048,
            )
        except Exception as exc:
            raise RuntimeError(
                f"LiteLLM completion failed for model {assignment.model_id!r}: {exc}"
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000
        result_text = response.choices[0].message.content or ""

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

        usage = getattr(response, "usage", None)
        raw_usage: dict[str, Any] = {}
        token_cost = 0.0
        if usage is not None:
            total_tokens = getattr(usage, "total_tokens", 0) or 0
            raw_usage = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": total_tokens,
            }
            token_cost = (total_tokens / 1000.0) * self._FALLBACK_COST_PER_1K

        return AgentResult(
            text=result_text,
            latency_ms=latency_ms,
            token_cost=token_cost,
            raw_usage=raw_usage,
        )

    def __repr__(self) -> str:
        return "AgentExecutor()"
