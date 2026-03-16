"""Summarizing memory is the compaction-job analogue that condenses old context while preserving recent turns."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, MutableMapping, Sequence

from KubeAI.templates.base import Template

_Summarizer = Callable[[Sequence[dict[str, Any]]], str]


class SummarizingMemory(Template):
    """Token-aware summarization policy that preserves recent conversational turns."""

    def __init__(self, token_threshold: int = 1500, keep_recent_turns: int = 10) -> None:
        super().__init__(name="summarizing")
        self.token_threshold = max(1, token_threshold)
        self.keep_recent_turns = max(1, keep_recent_turns)
        self._summarizer: _Summarizer | None = None

    def __repr__(self) -> str:
        return (
            "SummarizingMemory("
            f"token_threshold={self.token_threshold}, "
            f"keep_recent_turns={self.keep_recent_turns})"
        )

    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        self.configure(config)
        if config:
            if "token_threshold" in config:
                self.token_threshold = max(1, int(config["token_threshold"]))
            if "keep_recent_turns" in config:
                self.keep_recent_turns = max(1, int(config["keep_recent_turns"]))

            candidate = config.get("summarizer")
            if callable(candidate):
                self._summarizer = candidate

        if self._summarizer is None:
            agent_summarizer = getattr(agent, "summarize_history", None)
            if callable(agent_summarizer):
                self._summarizer = agent_summarizer

        if self._summarizer is None:
            agent_summarizer = getattr(agent, "summarizer", None)
            if callable(agent_summarizer):
                self._summarizer = agent_summarizer

        setattr(agent, "memory_template", self)

    def apply(self, history: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        if not history:
            return []

        if self._estimate_tokens(history) <= self.token_threshold:
            return [dict(message) for message in history]

        if len(history) <= self.keep_recent_turns:
            return [dict(message) for message in history]

        older = history[: -self.keep_recent_turns]
        recent = history[-self.keep_recent_turns :]

        summary_text = self._summarize(older)
        if not summary_text:
            return [dict(message) for message in recent]

        summary_message = {
            "role": "system",
            "content": f"Summary of earlier context: {summary_text}",
        }
        return [summary_message, *[dict(message) for message in recent]]

    @staticmethod
    def _estimate_tokens(history: Sequence[dict[str, Any]]) -> int:
        """Estimate token count using a lightweight whitespace heuristic."""
        total = 0
        for message in history:
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            total += len(role.split()) + len(content.split()) + 2
        return total

    def _summarize(self, history: Sequence[dict[str, Any]]) -> str:
        if self._summarizer is not None:
            try:
                generated = self._summarizer(history)
                if isinstance(generated, str) and generated.strip():
                    return generated.strip()
            except Exception:
                pass

        return self._heuristic_summary(history)

    def _heuristic_summary(self, history: Sequence[dict[str, Any]]) -> str:
        """Deterministic fallback summarizer used when runtime summarizer is unavailable."""
        parts: list[str] = []
        for message in history:
            role = str(message.get("role", "unknown"))
            content = str(message.get("content", "")).strip()
            if content:
                parts.append(f"[{role}] {content}")

        joined = " | ".join(parts)
        if not joined:
            return ""

        max_words = max(40, self.token_threshold // 2)
        words = joined.split()
        if len(words) <= max_words:
            return joined
        return " ".join(words[:max_words])
