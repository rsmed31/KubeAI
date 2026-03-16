"""Scraper RAG is the DaemonSet sidecar analogue that ingests web content and feeds retrieval-ready chunks into agent context."""

from __future__ import annotations

import re
from typing import Any, Iterable, MutableMapping

from KubeAI.scraper.chunker import chunk_texts
from KubeAI.scraper.pipeline import RAGScraper, ScrapeResult
from KubeAI.templates.base import Template

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class ScraperRAG(Template):
    """Template wrapper around RAGScraper that supports attach-time ingestion workflows."""

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        timeout: int = 10,
        user_agent: str = "KubeAI-Scraper/1.0",
        max_local_chunks: int = 3000,
        scraper: Any | None = None,
    ) -> None:
        super().__init__(name="scraper")
        self.chunk_size = max(1, chunk_size)
        self.overlap = max(0, overlap)
        self.timeout = max(1, timeout)
        self.user_agent = user_agent
        self.max_local_chunks = max(1, max_local_chunks)
        self._injected_scraper = scraper
        self._scraper: Any = scraper or RAGScraper(
            chunk_size=self.chunk_size,
            overlap=self.overlap,
            timeout=self.timeout,
            user_agent=self.user_agent,
        )
        self._local_chunks: list[str] = []
        self._target_rag: Any | None = None

    def __repr__(self) -> str:
        return (
            "ScraperRAG("
            f"chunk_size={self.chunk_size}, "
            f"overlap={self.overlap}, "
            f"timeout={self.timeout}, "
            f"local_chunks={len(self._local_chunks)})"
        )

    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        self.configure(config)
        if config:
            if "chunk_size" in config:
                self.chunk_size = max(1, int(config["chunk_size"]))
            if "overlap" in config:
                self.overlap = max(0, int(config["overlap"]))
            if "timeout" in config:
                self.timeout = max(1, int(config["timeout"]))
            if "user_agent" in config:
                self.user_agent = str(config["user_agent"]) or self.user_agent
            if "max_local_chunks" in config:
                self.max_local_chunks = max(1, int(config["max_local_chunks"]))

            target_candidate = config.get("target_rag")
            if target_candidate is not None and hasattr(target_candidate, "add_documents"):
                self._target_rag = target_candidate

        if self._target_rag is None:
            agent_target = getattr(agent, "downstream_rag_template", None)
            if agent_target is not None and hasattr(agent_target, "add_documents"):
                self._target_rag = agent_target

        if self._injected_scraper is None:
            self._scraper = RAGScraper(
                chunk_size=self.chunk_size,
                overlap=self.overlap,
                timeout=self.timeout,
                user_agent=self.user_agent,
            )
        setattr(agent, "rag_template", self)

    def add_documents(self, docs: Iterable[str]) -> None:
        """Ingest plain text documents and chunk them for fallback local retrieval."""
        incoming = [text for text in docs if text]
        if not incoming:
            return
        chunks = chunk_texts(incoming, chunk_size=self.chunk_size, overlap=self.overlap)
        self._append_chunks(chunks)

    def scrape_url(self, url: str) -> ScrapeResult:
        """Scrape one URL and return a structured result from the scraper pipeline."""
        return self._scraper.scrape_url(url)

    def scrape_urls(self, urls: Iterable[str]) -> list[ScrapeResult]:
        """Scrape many URLs sequentially and return one result per URL."""
        return self._scraper.scrape_urls(list(urls))

    def scrape_and_load(
        self,
        urls: Iterable[str],
        rag_template: Any | None = None,
    ) -> int:
        """Scrape URLs and load chunks either into target RAG or local fallback store."""
        results = self.scrape_urls(urls)
        target = rag_template or self._target_rag

        if target is not None and hasattr(target, "add_documents"):
            return int(self._scraper.load_into_rag(results, target))

        loaded = 0
        for result in results:
            if result.ok and result.chunks:
                self._append_chunks(result.chunks)
                loaded += result.chunk_count
        return loaded

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """Return top local chunks ranked by lexical overlap with query tokens."""
        if not query or top_k <= 0 or not self._local_chunks:
            return []

        query_tokens = set(_TOKEN_PATTERN.findall(query.lower()))
        if not query_tokens:
            return []

        scored: list[tuple[float, str]] = []
        for chunk in self._local_chunks:
            chunk_tokens = set(_TOKEN_PATTERN.findall(chunk.lower()))
            if not chunk_tokens:
                continue
            overlap = len(query_tokens.intersection(chunk_tokens))
            if overlap == 0:
                continue
            score = float(overlap) / float(len(query_tokens.union(chunk_tokens)))
            scored.append((score, chunk))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [chunk for _, chunk in scored[:top_k]]

    def list_local_chunks(self) -> list[str]:
        """Return a copy of locally retained chunks for observability and tests."""
        return list(self._local_chunks)

    def _append_chunks(self, chunks: Iterable[str]) -> None:
        for chunk in chunks:
            if chunk:
                self._local_chunks.append(chunk)
        if len(self._local_chunks) > self.max_local_chunks:
            self._local_chunks = self._local_chunks[-self.max_local_chunks :]
