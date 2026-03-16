"""Episodic memory is the event-log analogue that stores facts and recalls only relevant episodes per task."""

from __future__ import annotations

import re
from typing import Any, MutableMapping, Sequence

from KubeAI.templates.base import Template

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


class EpisodicMemory(Template):
    """Episodic fact memory with lightweight extraction and similarity retrieval."""

    def __init__(
        self,
        max_facts: int = 200,
        similarity_threshold: float = 0.1,
        min_fact_tokens: int = 3,
    ) -> None:
        super().__init__(name="episodic")
        self.max_facts = max(1, max_facts)
        self.similarity_threshold = max(0.0, similarity_threshold)
        self.min_fact_tokens = max(1, min_fact_tokens)
        self._facts: list[dict[str, Any]] = []

    def __repr__(self) -> str:
        return (
            "EpisodicMemory("
            f"facts={len(self._facts)}, "
            f"max_facts={self.max_facts}, "
            f"similarity_threshold={self.similarity_threshold}, "
            f"min_fact_tokens={self.min_fact_tokens})"
        )

    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        self.configure(config)
        if config:
            if "max_facts" in config:
                self.max_facts = max(1, int(config["max_facts"]))
            if "similarity_threshold" in config:
                self.similarity_threshold = max(0.0, float(config["similarity_threshold"]))
            if "min_fact_tokens" in config:
                self.min_fact_tokens = max(1, int(config["min_fact_tokens"]))
        setattr(agent, "memory_template", self)

    def ingest_turn(self, role: str, content: str) -> None:
        content = content.strip()
        if not content:
            return

        for sentence in _SENTENCE_SPLIT.split(content):
            sentence = sentence.strip()
            if not sentence:
                continue

            tokens = _tokenize(sentence)
            if len(tokens) < self.min_fact_tokens:
                continue

            self._facts.append(
                {
                    "text": f"[{role}] {sentence}",
                    "tokens": tokens,
                }
            )

        if len(self._facts) > self.max_facts:
            overflow = len(self._facts) - self.max_facts
            self._facts = self._facts[overflow:]

    def retrieve_facts(self, query: str, top_k: int = 5) -> list[str]:
        if not query or top_k <= 0 or not self._facts:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, str]] = []
        for fact in self._facts:
            text = str(fact["text"])
            tokens = set(fact["tokens"])
            if not tokens:
                continue
            overlap = len(query_tokens.intersection(tokens))
            union = len(query_tokens.union(tokens))
            score = (float(overlap) / float(union)) if union else 0.0
            if score >= self.similarity_threshold:
                scored.append((score, text))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [fact for _, fact in scored[:top_k]]

    def apply(self, history: Sequence[dict[str, Any]], query: str, top_k: int = 5) -> list[dict[str, Any]]:
        relevant = self.retrieve_facts(query=query, top_k=top_k)
        if not relevant:
            return [dict(message) for message in history]

        episodic_payload = {
            "role": "system",
            "content": "Relevant episodic facts:\n" + "\n".join(f"- {item}" for item in relevant),
        }
        return [episodic_payload, *[dict(message) for message in history]]
