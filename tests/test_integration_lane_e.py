"""Lane E integration tests for template composition, README command parity, and demo flow integrity."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from KubeAI.templates.base import attach_templates
from KubeAI.templates.memory.summarizing import SummarizingMemory
from KubeAI.templates.rag.basic import BasicRAG
from examples.demo import run_demo


@dataclass
class _Agent:
    """Simple attach target for integration tests."""


class TestLaneEIntegration:
    def test_rag_and_memory_templates_compose(self) -> None:
        agent = _Agent()
        rag = BasicRAG()
        memory = SummarizingMemory(token_threshold=10, keep_recent_turns=2)

        attached = attach_templates(
            agent,
            [rag, memory],
            configs={
                "basic": {"top_k": 2, "similarity_threshold": 0.0},
                "summarizing": {"token_threshold": 10, "keep_recent_turns": 2},
            },
        )

        assert set(attached) == {"basic", "summarizing"}
        assert getattr(agent, "rag_template") is rag
        assert getattr(agent, "memory_template") is memory

        rag.add_documents(
            [
                "KubeAI orchestrator routes tasks semantically.",
                "Agent templates compose retrieval and memory behavior.",
            ]
        )
        retrieved = rag.retrieve("semantic routing", top_k=1)
        assert retrieved

        history = [
            {"role": "user", "content": "Discuss orchestration architecture and routing choices."},
            {"role": "assistant", "content": "KubeAI uses orchestrator scoring and pool assignment."},
            {"role": "user", "content": "How do templates compose?"},
            {"role": "assistant", "content": "Attach both RAG and memory templates at spawn."},
        ]
        summarized = memory.apply(history)
        assert summarized
        assert summarized[0]["role"] == "system"

    def test_readme_lists_supported_cli_commands(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        expected = [
            "agentctl run",
            "agentctl blueprints list",
            "agentctl blueprints register",
            "agentctl templates list",
            "agentctl mcps list",
            "agentctl mcps register",
            "agentctl status",
            "agentctl demo",
        ]
        for command in expected:
            assert command in readme

    def test_example_demo_runs_and_outputs_flow(self) -> None:
        output = run_demo()
        assert "KubeAI demo command flow" in output
        assert "agentctl templates list" in output
        assert "agentctl status" in output
