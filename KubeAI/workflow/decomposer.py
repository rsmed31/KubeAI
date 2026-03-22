"""TaskDecomposer — splits complex tasks into typed sub-tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Keyword signals for each task type
_TYPE_SIGNALS: dict[str, list[str]] = {
    "codegen": [
        "write", "implement", "code", "function", "class", "script",
        "program", "algorithm", "debug", "fix bug", "refactor",
    ],
    "rag": [
        "find", "retrieve", "search", "look up", "query", "what is",
        "who is", "when did", "where is", "document", "reference",
    ],
    "research": [
        "analyze", "research", "investigate", "explain", "describe",
        "summarize", "compare", "evaluate", "survey", "report",
    ],
    "data_analysis": [
        "data", "csv", "statistics", "average", "mean", "calculate",
        "plot", "chart", "dataset", "aggregate", "count", "filter",
    ],
}


def classify_task(description: str) -> str:
    """Classify a task description into one of 4 scenario types.

    Returns one of: 'rag', 'codegen', 'research', 'data_analysis'.
    Defaults to 'research' for ambiguous tasks.
    """
    lower = description.lower()
    scores: dict[str, int] = {t: 0 for t in _TYPE_SIGNALS}
    for task_type, keywords in _TYPE_SIGNALS.items():
        for kw in keywords:
            if kw in lower:
                scores[task_type] += 1
    # Return type with most keyword hits; fallback to 'research'
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "research"


@dataclass
class SubTask:
    """A decomposed unit of work with a classified type."""
    description: str
    task_type: str  # 'rag' | 'codegen' | 'research' | 'data_analysis'
    index: int = 0


class TaskDecomposer:
    """Splits a complex task into typed sub-tasks for parallel execution.

    Analogous to how Kubernetes breaks a DaemonSet rollout into per-node
    sub-operations — each sub-task can use a different framework adapter.
    """

    # Patterns that suggest a natural decomposition boundary
    _STEP_PATTERNS = [
        re.compile(r'^\s*\d+[\.\)]\s+', re.MULTILINE),   # "1. do X"
        re.compile(r'^\s*[-*]\s+', re.MULTILINE),          # "- do X"
        re.compile(r'\bthen\b', re.IGNORECASE),
        re.compile(r'\bafter(?:ward)?\b', re.IGNORECASE),
        re.compile(r'\bfinally\b', re.IGNORECASE),
        re.compile(r'\band also\b', re.IGNORECASE),
    ]

    def should_decompose(self, description: str) -> bool:
        """Return True if the task appears to have multiple distinct steps."""
        for pattern in self._STEP_PATTERNS:
            if pattern.search(description):
                return True
        # Heuristic: very long tasks are likely multi-step
        return len(description) > 500

    def decompose(self, description: str) -> list[SubTask]:
        """Split description into sub-tasks, each with a classified type.

        If decomposition isn't possible or appropriate, returns a single
        sub-task covering the whole description.
        """
        if not self.should_decompose(description):
            return [SubTask(
                description=description,
                task_type=classify_task(description),
                index=0,
            )]

        parts = self._split(description)
        if len(parts) <= 1:
            return [SubTask(
                description=description,
                task_type=classify_task(description),
                index=0,
            )]

        return [
            SubTask(description=part.strip(), task_type=classify_task(part), index=i)
            for i, part in enumerate(parts)
            if part.strip()
        ]

    def _split(self, description: str) -> list[str]:
        """Split description on list markers or 'then'/'and also' connectors."""
        # Try splitting on numbered/bullet list items first
        for pattern in self._STEP_PATTERNS[:2]:
            matches = list(pattern.finditer(description))
            if len(matches) >= 2:
                parts: list[str] = []
                for i, match in enumerate(matches):
                    start = match.end()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(description)
                    parts.append(description[start:end].strip())
                return [p for p in parts if p]

        # Fallback: split on sentence-level connectors
        for connector in [r'\bthen\b', r'\band also\b']:
            parts = re.split(connector, description, flags=re.IGNORECASE)
            if len(parts) >= 2:
                return [p.strip() for p in parts if p.strip()]

        return [description]
