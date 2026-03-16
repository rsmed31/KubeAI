"""Document probe is the readiness-check analogue that samples payloads to infer routing and capability requirements."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_PATTERN = re.compile(r"\S+")

_KEYWORD_TO_CAPABILITY = {
    "http": "fetch_url",
    "https": "fetch_url",
    "url": "fetch_url",
    "web": "web_search",
    "api": "web_search",
    "code": "code_exec",
    "python": "code_exec",
    "json": "data_processing",
    "csv": "data_processing",
    "table": "data_processing",
    "sql": "db_query",
    "database": "db_query",
    "graph": "knowledge_graph",
    "entity": "knowledge_graph",
}


@dataclass(frozen=True)
class ProbedDocument:
    """Structured probe result used to dispatch document tasks."""

    sample: str
    preview: str
    estimated_tokens: int
    cost_hint: float
    required_capabilities: tuple[str, ...]

    def __repr__(self) -> str:
        return (
            f"ProbedDocument(tokens={self.estimated_tokens}, cost_hint={self.cost_hint:.2f}, "
            f"capabilities={self.required_capabilities!r})"
        )


class DocumentProbe:
    """Sample documents and infer deterministic routing hints."""

    def __init__(self, sample_chars: int = 600, preview_chars: int = 240) -> None:
        self.sample_chars = max(32, sample_chars)
        self.preview_chars = max(16, preview_chars)

    def probe(self, document: str) -> ProbedDocument:
        """Probe a document and infer complexity and required capability tags."""
        normalized = document.strip()
        if not normalized:
            raise ValueError("document must not be empty")

        sample = normalized[: self.sample_chars]
        preview = normalized[: self.preview_chars]
        token_count = self.estimate_tokens(sample)
        required = self.infer_capabilities(sample)
        cost_hint = self.estimate_cost_hint(token_count=token_count, capabilities=required)

        return ProbedDocument(
            sample=sample,
            preview=preview,
            estimated_tokens=token_count,
            cost_hint=cost_hint,
            required_capabilities=tuple(required),
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count using a whitespace heuristic."""
        return len(_TOKEN_PATTERN.findall(text))

    @staticmethod
    def infer_capabilities(text: str) -> list[str]:
        """Infer required capability tags from keyword signals."""
        lowered = text.lower()
        found: set[str] = {"rag_retrieval"}
        for keyword, capability in _KEYWORD_TO_CAPABILITY.items():
            if keyword in lowered:
                found.add(capability)
        return sorted(found)

    @staticmethod
    def estimate_cost_hint(*, token_count: int, capabilities: list[str]) -> float:
        """Map probe signals to a 0.0-1.0 complexity hint for assignment."""
        token_signal = min(1.0, float(token_count) / 240.0)
        capability_signal = min(1.0, float(max(0, len(capabilities) - 1)) * 0.15)
        combined = 0.15 + 0.55 * token_signal + 0.30 * capability_signal
        return max(0.0, min(1.0, combined))

    def __repr__(self) -> str:
        return (
            f"DocumentProbe(sample_chars={self.sample_chars}, "
            f"preview_chars={self.preview_chars})"
        )
