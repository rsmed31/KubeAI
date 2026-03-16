"""RAGScraper is the DaemonSet analogue: runs continuously to ingest web content into the distributed RAG index."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .chunker import chunk_texts
from .extractor import extract_text
from .fetcher import FetchResult, fetch


@dataclass
class ScrapeResult:
    """
    The outcome of scraping a single URL.

    Analogous to a DaemonSet pod status report: records whether the fetch
    succeeded, how many chunks were produced, and any error that occurred so
    the caller can decide how to handle failures without raising exceptions.
    """

    url: str
    chunks: list[str]
    chunk_count: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Return True if the scrape completed without error."""
        return self.error is None

    def __repr__(self) -> str:
        return (
            f"ScrapeResult(url={self.url!r}, chunk_count={self.chunk_count}, "
            f"ok={self.ok})"
        )


class RAGScraper:
    """
    Orchestrates the fetch → extract → chunk → optional RAG load pipeline.

    Analogous to a Kubernetes DaemonSet: ensures web content is continuously
    ingested and indexed across the distributed RAG layer. Each scrape call
    is fully self-contained and never raises — errors are surfaced through
    ScrapeResult.error.

    Usage::

        scraper = RAGScraper(chunk_size=400, overlap=40)
        results = scraper.scrape_urls(["https://example.com"])
        total = scraper.load_into_rag(results, my_rag_template)
    """

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        timeout: int = 10,
        user_agent: str = "KubeAI-Scraper/1.0",
    ) -> None:
        """
        Initialise the RAGScraper.

        Args:
            chunk_size: Target number of words per text chunk.
            overlap: Number of words shared between adjacent chunks.
            timeout: HTTP fetch timeout in seconds.
            user_agent: User-Agent header sent with every request.
        """
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._timeout = timeout
        self._user_agent = user_agent

    def scrape_url(self, url: str) -> ScrapeResult:
        """
        Fetch one URL, extract text, and split into chunks.

        Never raises. If the HTTP fetch fails or extraction produces no text,
        the returned ScrapeResult will have ok=False and error set.

        Args:
            url: The URL to scrape.

        Returns:
            A ScrapeResult with the text chunks (or error details).
        """
        try:
            result: FetchResult = fetch(url, timeout=self._timeout, user_agent=self._user_agent)
            if not result.ok:
                return ScrapeResult(
                    url=url,
                    chunks=[],
                    chunk_count=0,
                    error=result.error or f"HTTP {result.status_code}",
                )
            text = extract_text(result.content)
            chunks = chunk_texts([text], chunk_size=self._chunk_size, overlap=self._overlap)
            return ScrapeResult(url=url, chunks=chunks, chunk_count=len(chunks))
        except Exception as exc:  # pragma: no cover — defensive catch-all
            return ScrapeResult(url=url, chunks=[], chunk_count=0, error=str(exc))

    def scrape_urls(self, urls: list[str]) -> list[ScrapeResult]:
        """
        Fetch multiple URLs sequentially and return all ScrapeResults.

        Args:
            urls: List of URLs to scrape.

        Returns:
            A list of ScrapeResult objects in the same order as urls.
        """
        return [self.scrape_url(url) for url in urls]

    def load_into_rag(self, results: list[ScrapeResult], rag_template: Any) -> int:
        """
        Load all successful scrape results into a RAG template.

        Calls rag_template.add_documents(chunks) for each ScrapeResult that
        has ok=True and at least one chunk. Failed results are silently skipped.

        Args:
            results: List of ScrapeResult objects (typically from scrape_urls).
            rag_template: Any object exposing add_documents(docs: list[str]).

        Returns:
            Total number of chunks loaded across all successful results.
        """
        total = 0
        for result in results:
            if result.ok and result.chunks:
                rag_template.add_documents(result.chunks)
                total += result.chunk_count
        return total

    def scrape_and_load(self, urls: list[str], rag_template: Any) -> int:
        """
        Scrape multiple URLs and load all successful results into a RAG template.

        Convenience method equivalent to calling scrape_urls() followed by
        load_into_rag().

        Args:
            urls: List of URLs to scrape.
            rag_template: Any object exposing add_documents(docs: list[str]).

        Returns:
            Total number of chunks loaded.
        """
        results = self.scrape_urls(urls)
        return self.load_into_rag(results, rag_template)

    def __repr__(self) -> str:
        return (
            f"RAGScraper(chunk_size={self._chunk_size}, overlap={self._overlap}, "
            f"timeout={self._timeout})"
        )
