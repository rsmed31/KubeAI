"""Unit tests for ScraperRAG template integration layer (Lane G)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from KubeAI.scraper.pipeline import ScrapeResult
from KubeAI.templates.rag.scraper import ScraperRAG


@dataclass
class _Agent:
    """Simple attach target for template tests."""


class _FakeScraper:
    """Deterministic scraper stub for testing ScraperRAG wiring."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def scrape_url(self, url: str) -> ScrapeResult:
        return ScrapeResult(url=url, chunks=[f"chunk:{url}"], chunk_count=1)

    def scrape_urls(self, urls: list[str]) -> list[ScrapeResult]:
        self.calls.append(list(urls))
        return [ScrapeResult(url=url, chunks=[f"chunk:{url}"], chunk_count=1) for url in urls]

    def load_into_rag(self, results: list[ScrapeResult], rag_template: Any) -> int:
        total = 0
        for result in results:
            if result.ok and result.chunks:
                rag_template.add_documents(result.chunks)
                total += result.chunk_count
        return total


class _FakeTargetRAG:
    def __init__(self) -> None:
        self.documents: list[str] = []

    def add_documents(self, docs: list[str]) -> None:
        self.documents.extend(docs)


class TestScraperRAG:
    def test_attach_sets_agent_rag_template(self) -> None:
        template = ScraperRAG(scraper=_FakeScraper())
        agent = _Agent()

        template.attach(agent, {"chunk_size": 128, "overlap": 8})
        assert getattr(agent, "rag_template") is template

    def test_scrape_and_load_without_target_uses_local_store(self) -> None:
        template = ScraperRAG(scraper=_FakeScraper())
        template.attach(_Agent(), None)

        loaded = template.scrape_and_load(["https://example.com/a", "https://example.com/b"])
        assert loaded == 2

        chunks = template.list_local_chunks()
        assert len(chunks) == 2
        assert any("example.com/a" in chunk for chunk in chunks)

    def test_scrape_and_load_with_target_rag_forwards_chunks(self) -> None:
        target = _FakeTargetRAG()
        template = ScraperRAG(scraper=_FakeScraper())
        template.attach(_Agent(), {"target_rag": target})

        loaded = template.scrape_and_load(["https://example.com/doc"])
        assert loaded == 1
        assert target.documents == ["chunk:https://example.com/doc"]

    def test_add_documents_and_retrieve(self) -> None:
        template = ScraperRAG(scraper=_FakeScraper())
        template.attach(_Agent(), {"chunk_size": 4, "overlap": 1})

        template.add_documents(
            [
                "KubeAI orchestrator routes tasks using semantic scoring",
                "RAG scraper ingests web context for retrieval",
            ]
        )
        results = template.retrieve("semantic retrieval", top_k=2)

        assert results
        assert len(results) <= 2
