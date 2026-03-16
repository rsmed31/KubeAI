"""Knowledge graph RAG is the topology-controller analogue that builds entity-relation structure from documents for graph-guided retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, MutableMapping

from KubeAI.templates.base import Template

_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_SENTENCE_PATTERN = re.compile(r"[^.!?\n]+")

_DOMAIN_ENTITY_HINTS = {
    "kubeai",
    "kubernetes",
    "orchestrator",
    "scheduler",
    "agent",
    "agents",
    "memory",
    "redis",
    "sqlite",
    "python",
    "mcp",
    "rag",
    "llm",
}

_RELATION_MAP = {
    "uses": "uses",
    "use": "uses",
    "contains": "contains",
    "includes": "contains",
    "stores": "stores",
    "routes": "routes_to",
    "connects": "connects_to",
    "calls": "calls",
    "spawns": "spawns",
    "runs": "runs",
}


@dataclass(frozen=True)
class GraphRelation:
    """Directed graph edge extracted from one sentence."""

    source: str
    predicate: str
    target: str
    weight: float = 1.0

    def __repr__(self) -> str:
        return (
            "GraphRelation("
            f"source={self.source!r}, "
            f"predicate={self.predicate!r}, "
            f"target={self.target!r}, "
            f"weight={self.weight:.2f})"
        )


class KnowledgeGraphRAG(Template):
    """Build and query a lightweight knowledge graph from ingested documents."""

    def __init__(
        self,
        max_nodes: int = 500,
        max_edges: int = 2000,
        min_entity_chars: int = 3,
    ) -> None:
        super().__init__(name="knowledge_graph")
        self.max_nodes = max(1, max_nodes)
        self.max_edges = max(1, max_edges)
        self.min_entity_chars = max(1, min_entity_chars)
        self._node_counts: dict[str, int] = {}
        self._edge_counts: dict[tuple[str, str, str], int] = {}

    def __repr__(self) -> str:
        return (
            "KnowledgeGraphRAG("
            f"nodes={len(self._node_counts)}, "
            f"edges={len(self._edge_counts)}, "
            f"max_nodes={self.max_nodes}, "
            f"max_edges={self.max_edges})"
        )

    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        self.configure(config)
        if config:
            if "max_nodes" in config:
                self.max_nodes = max(1, int(config["max_nodes"]))
            if "max_edges" in config:
                self.max_edges = max(1, int(config["max_edges"]))
            if "min_entity_chars" in config:
                self.min_entity_chars = max(1, int(config["min_entity_chars"]))
        setattr(agent, "rag_template", self)

    def add_documents(self, docs: Iterable[str]) -> None:
        """Extract entity and relation signals from a document collection."""
        for doc in docs:
            if not doc:
                continue
            for sentence in _SENTENCE_PATTERN.findall(doc):
                sentence = sentence.strip()
                if not sentence:
                    continue
                entities = self.extract_entities(sentence)
                for entity in entities:
                    self._increment_node(entity)
                for relation in self.extract_relations(sentence):
                    self._increment_edge(relation)

    def extract_entities(self, text: str) -> list[str]:
        """Return deduplicated entity names from one text span."""
        tokens = _TOKEN_PATTERN.findall(text)
        entities: list[str] = []
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token[0].isupper():
                group = [token]
                idx += 1
                while idx < len(tokens) and tokens[idx][0].isupper():
                    group.append(tokens[idx])
                    idx += 1
                candidate = " ".join(group)
                if len(candidate) >= self.min_entity_chars:
                    entities.append(candidate)
                continue

            lowered = token.lower()
            if lowered in _DOMAIN_ENTITY_HINTS and len(lowered) >= self.min_entity_chars:
                entities.append(lowered)
            idx += 1

        # Stable dedupe preserving first-seen order.
        deduped: list[str] = []
        seen: set[str] = set()
        for entity in entities:
            normalized = entity.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped

    def extract_relations(self, sentence: str) -> list[GraphRelation]:
        """Extract one deterministic relation edge from a sentence when possible."""
        tokens = _TOKEN_PATTERN.findall(sentence)
        if not tokens:
            return []

        entities_with_position = self._entities_with_positions(tokens)
        if len(entities_with_position) < 2:
            return []

        predicate, relation_index = self._find_predicate(tokens)
        if relation_index is None:
            source = entities_with_position[0][1]
            target = entities_with_position[1][1]
            return [GraphRelation(source=source, predicate="related_to", target=target)]

        source = ""
        target = ""
        for index, entity in reversed(entities_with_position):
            if index < relation_index:
                source = entity
                break
        for index, entity in entities_with_position:
            if index > relation_index:
                target = entity
                break

        if not source or not target:
            source = entities_with_position[0][1]
            target = entities_with_position[1][1]

        return [GraphRelation(source=source, predicate=predicate, target=target)]

    def retrieve(self, query: str, top_k: int = 5) -> list[str]:
        """Retrieve top relation strings scored by lexical overlap with query."""
        if not query or top_k <= 0 or not self._edge_counts:
            return []

        query_tokens = {token.lower() for token in _TOKEN_PATTERN.findall(query)}
        query_entities = {entity.lower() for entity in self.extract_entities(query)}

        scored: list[tuple[float, str]] = []
        for (source, predicate, target), count in self._edge_counts.items():
            edge_tokens = {
                *{token.lower() for token in _TOKEN_PATTERN.findall(source)},
                predicate.lower(),
                *{token.lower() for token in _TOKEN_PATTERN.findall(target)},
            }
            overlap = len(edge_tokens.intersection(query_tokens))
            entity_bonus = 0.0
            if source.lower() in query_entities or target.lower() in query_entities:
                entity_bonus = 1.0
            score = float(count) + float(overlap) + entity_bonus
            rendered = f"{source} --{predicate}--> {target}"
            scored.append((score, rendered))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item for _, item in scored[:top_k]]

    def neighbors(self, entity: str, top_k: int = 5) -> list[GraphRelation]:
        """Return relations connected to an entity ordered by edge frequency."""
        if not entity or top_k <= 0:
            return []

        key = entity.lower()
        collected: list[tuple[int, GraphRelation]] = []
        for (source, predicate, target), count in self._edge_counts.items():
            if source.lower() == key or target.lower() == key:
                collected.append(
                    (
                        count,
                        GraphRelation(
                            source=source,
                            predicate=predicate,
                            target=target,
                            weight=float(count),
                        ),
                    )
                )

        collected.sort(key=lambda item: (-item[0], item[1].source, item[1].target, item[1].predicate))
        return [relation for _, relation in collected[:top_k]]

    def serialize_graph(self) -> dict[str, list[dict[str, Any]]]:
        """Serialize graph nodes and edges into deterministic sorted payload."""
        nodes = [
            {"id": name, "count": count}
            for name, count in sorted(self._node_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        edges = [
            {
                "source": source,
                "predicate": predicate,
                "target": target,
                "count": count,
            }
            for (source, predicate, target), count in sorted(
                self._edge_counts.items(),
                key=lambda item: (-item[1], item[0][0], item[0][1], item[0][2]),
            )
        ]
        return {"nodes": nodes, "edges": edges}

    def _increment_node(self, entity: str) -> None:
        self._node_counts[entity] = self._node_counts.get(entity, 0) + 1
        if len(self._node_counts) <= self.max_nodes:
            return
        # Keep most frequent nodes and drop least frequent to respect bounds.
        victim = min(self._node_counts.items(), key=lambda item: (item[1], item[0]))[0]
        del self._node_counts[victim]
        # Drop edges referencing evicted nodes.
        stale_edges = [
            key
            for key in self._edge_counts
            if key[0] == victim or key[2] == victim
        ]
        for key in stale_edges:
            del self._edge_counts[key]

    def _increment_edge(self, relation: GraphRelation) -> None:
        key = (relation.source, relation.predicate, relation.target)
        self._edge_counts[key] = self._edge_counts.get(key, 0) + 1
        if len(self._edge_counts) <= self.max_edges:
            return
        victim = min(self._edge_counts.items(), key=lambda item: (item[1], item[0]))[0]
        del self._edge_counts[victim]

    def _entities_with_positions(self, tokens: list[str]) -> list[tuple[int, str]]:
        """Return entity candidates with token indices for relation extraction."""
        entities: list[tuple[int, str]] = []
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token[0].isupper():
                start = idx
                group = [token]
                idx += 1
                while idx < len(tokens) and tokens[idx][0].isupper():
                    group.append(tokens[idx])
                    idx += 1
                entity = " ".join(group)
                if len(entity) >= self.min_entity_chars:
                    entities.append((start, entity))
                continue

            lowered = token.lower()
            if lowered in _DOMAIN_ENTITY_HINTS and len(lowered) >= self.min_entity_chars:
                entities.append((idx, lowered))
            idx += 1
        return entities

    @staticmethod
    def _find_predicate(tokens: list[str]) -> tuple[str, int | None]:
        lowered_tokens = [token.lower() for token in tokens]
        for idx, token in enumerate(lowered_tokens):
            if token == "depends" and idx + 1 < len(lowered_tokens) and lowered_tokens[idx + 1] == "on":
                return "depends_on", idx
            if token == "routes" and idx + 1 < len(lowered_tokens) and lowered_tokens[idx + 1] == "to":
                return "routes_to", idx
            if token == "connects" and idx + 1 < len(lowered_tokens) and lowered_tokens[idx + 1] == "to":
                return "connects_to", idx
            if token in _RELATION_MAP:
                return _RELATION_MAP[token], idx
            if token in {"is", "are"}:
                return "is", idx
        return "related_to", None
