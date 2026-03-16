"""Unit tests for memory template variants: sliding window, summarizing, and episodic."""

from __future__ import annotations

from dataclasses import dataclass

from KubeAI.templates.memory.episodic import EpisodicMemory
from KubeAI.templates.memory.sliding_window import SlidingWindowMemory
from KubeAI.templates.memory.summarizing import SummarizingMemory


@dataclass
class _Agent:
    """Simple attach target for template tests."""


def _history(turns: int) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for index in range(turns):
        role = "user" if index % 2 == 0 else "assistant"
        history.append(
            {
                "role": role,
                "content": f"Turn {index} discussing kubernetes and python architecture details",
            }
        )
    return history


class TestSlidingWindowMemory:
    def test_keeps_recent_turns_only(self) -> None:
        template = SlidingWindowMemory(window_size=2)
        template.attach(_Agent(), {"window_size": 2})

        result = template.apply(_history(5))
        assert len(result) == 2
        assert result[0]["content"].startswith("Turn 3")
        assert result[1]["content"].startswith("Turn 4")

    def test_empty_history(self) -> None:
        template = SlidingWindowMemory(window_size=3)
        assert template.apply([]) == []


class TestSummarizingMemory:
    def test_summarizes_old_turns_and_keeps_recent(self) -> None:
        template = SummarizingMemory(token_threshold=12, keep_recent_turns=2)
        template.attach(_Agent(), {"token_threshold": 12, "keep_recent_turns": 2})

        history = _history(6)
        result = template.apply(history)

        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[1]["content"] == history[-2]["content"]
        assert result[2]["content"] == history[-1]["content"]

    def test_custom_summarizer_callable(self) -> None:
        template = SummarizingMemory(token_threshold=10, keep_recent_turns=1)
        template.attach(_Agent(), {"token_threshold": 10, "summarizer": lambda _: "custom summary"})

        result = template.apply(_history(4))
        assert result[0]["content"] == "Summary of earlier context: custom summary"


class TestEpisodicMemory:
    def test_ingest_and_retrieve_relevant_facts(self) -> None:
        template = EpisodicMemory(max_facts=10, similarity_threshold=0.1)
        template.attach(_Agent(), {"similarity_threshold": 0.1, "min_fact_tokens": 2})

        template.ingest_turn("user", "KubeAI routes tasks through the orchestrator.")
        template.ingest_turn("assistant", "Templates are attached at spawn time for RAG and memory.")

        facts = template.retrieve_facts("how are templates attached", top_k=3)
        assert facts
        assert any("Templates are attached" in fact for fact in facts)

    def test_low_similarity_returns_empty(self) -> None:
        template = EpisodicMemory(max_facts=10, similarity_threshold=0.8)
        template.attach(_Agent(), {"similarity_threshold": 0.8, "min_fact_tokens": 2})

        template.ingest_turn("user", "KubeAI uses semantic routing for tasks.")
        assert template.retrieve_facts("quantum chemistry", top_k=3) == []

    def test_apply_injects_payload_when_relevant(self) -> None:
        template = EpisodicMemory(max_facts=10, similarity_threshold=0.1)
        template.attach(_Agent(), {"similarity_threshold": 0.1, "min_fact_tokens": 2})

        template.ingest_turn("user", "The scheduler can reuse idle agents to reduce latency.")
        history = _history(2)
        result = template.apply(history, query="idle agents", top_k=2)

        assert result[0]["role"] == "system"
        assert "Relevant episodic facts" in result[0]["content"]
        assert len(result) == len(history) + 1
