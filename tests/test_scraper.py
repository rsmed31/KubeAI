"""Unit tests for KubeAI RAG scraper components (Lane G).

Tests cover fetcher (via FetchResult stubs), extractor, chunker, and pipeline.
No real HTTP connections are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from KubeAI.scraper.chunker import Chunk, chunk_text, chunk_texts
from KubeAI.scraper.extractor import extract_links, extract_text
from KubeAI.scraper.fetcher import FetchResult, fetch
from KubeAI.scraper.pipeline import RAGScraper, ScrapeResult


# ---------------------------------------------------------------------------
# Extractor tests
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_removes_script_tags(self) -> None:
        html = "<html><body>Hello<script>alert('x')</script> world</body></html>"
        text = extract_text(html)
        assert "alert" not in text
        assert "Hello" in text
        assert "world" in text

    def test_removes_style_tags(self) -> None:
        html = "<html><body><style>body{color:red}</style>Visible text</body></html>"
        text = extract_text(html)
        assert "color" not in text
        assert "Visible text" in text

    def test_returns_body_text(self) -> None:
        html = "<html><body><p>The quick brown fox</p></body></html>"
        text = extract_text(html)
        assert "quick brown fox" in text

    def test_normalises_whitespace(self) -> None:
        html = "<html><body>  Multiple   spaces\n\nand\tnewlines  </body></html>"
        text = extract_text(html)
        # Should not contain multiple consecutive spaces
        assert "  " not in text
        assert "Multiple" in text

    def test_removes_nav_footer_aside(self) -> None:
        html = (
            "<html><body>"
            "<nav>Navigation junk</nav>"
            "<main>Main content</main>"
            "<footer>Footer junk</footer>"
            "<aside>Aside junk</aside>"
            "</body></html>"
        )
        text = extract_text(html)
        assert "Navigation junk" not in text
        assert "Footer junk" not in text
        assert "Aside junk" not in text
        assert "Main content" in text

    def test_removes_head_content(self) -> None:
        html = "<html><head><title>Page Title</title></head><body>Body text</body></html>"
        text = extract_text(html)
        # head content should be stripped
        assert "Page Title" not in text
        assert "Body text" in text

    def test_empty_html_returns_empty_string(self) -> None:
        text = extract_text("")
        assert text == ""

    def test_plain_text_returns_content(self) -> None:
        # When fed plain text (no tags), it should pass it through
        text = extract_text("Hello, world!")
        assert "Hello, world!" in text


class TestExtractLinks:
    def test_returns_absolute_links(self) -> None:
        html = '<html><body><a href="https://example.com/page">Link</a></body></html>'
        links = extract_links(html, base_url="https://example.com")
        assert "https://example.com/page" in links

    def test_resolves_relative_links(self) -> None:
        html = '<html><body><a href="/about">About</a></body></html>'
        links = extract_links(html, base_url="https://example.com")
        assert "https://example.com/about" in links

    def test_returns_multiple_links(self) -> None:
        html = (
            '<a href="https://a.com">A</a>'
            '<a href="https://b.com">B</a>'
            '<a href="https://c.com">C</a>'
        )
        links = extract_links(html, base_url="")
        assert len(links) == 3

    def test_empty_html_returns_empty_list(self) -> None:
        assert extract_links("", base_url="https://example.com") == []

    def test_no_links_returns_empty_list(self) -> None:
        html = "<html><body><p>No links here</p></body></html>"
        assert extract_links(html, base_url="https://example.com") == []


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_empty_string_returns_empty_list(self) -> None:
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert chunk_text("   \n\t  ") == []

    def test_short_text_returns_single_chunk(self) -> None:
        text = "This is a short sentence"
        chunks = chunk_text(text, chunk_size=500, overlap=0)
        assert len(chunks) == 1
        assert "short" in chunks[0].text

    def test_long_text_returns_multiple_chunks(self) -> None:
        # 30 words, chunk_size=10 → at least 3 chunks
        words = " ".join([f"word{i}" for i in range(30)])
        chunks = chunk_text(words, chunk_size=10, overlap=0)
        assert len(chunks) >= 3

    def test_chunks_have_correct_overlap(self) -> None:
        # Create 20 distinct words
        words = [f"w{i}" for i in range(20)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=10, overlap=3)
        assert len(chunks) >= 2
        # Consecutive chunks should share words (overlap > 0)
        words_0 = set(chunks[0].text.split())
        words_1 = set(chunks[1].text.split())
        shared = words_0 & words_1
        assert len(shared) > 0

    def test_overlap_zero_has_no_shared_words(self) -> None:
        words = [f"u{i}" for i in range(20)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=10, overlap=0)
        assert len(chunks) >= 2
        words_0 = set(chunks[0].text.split())
        words_1 = set(chunks[1].text.split())
        assert words_0.isdisjoint(words_1)

    def test_chunk_index_is_sequential(self) -> None:
        words = " ".join([f"x{i}" for i in range(30)])
        chunks = chunk_text(words, chunk_size=10, overlap=0)
        indices = [c.index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunk_char_start_less_than_char_end(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        chunks = chunk_text(text, chunk_size=5, overlap=0)
        for chunk in chunks:
            assert chunk.char_start <= chunk.char_end


class TestChunkRepr:
    def test_chunk_repr_includes_index(self) -> None:
        chunk = Chunk(text="hello world", index=3, char_start=0, char_end=11)
        r = repr(chunk)
        assert "3" in r
        assert "Chunk" in r


class TestChunkTexts:
    def test_chunk_texts_convenience_function_works(self) -> None:
        texts = ["Hello world " * 5, "Foo bar " * 5]
        result = chunk_texts(texts, chunk_size=5, overlap=0)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)
        assert len(result) > 0

    def test_chunk_texts_empty_list(self) -> None:
        assert chunk_texts([]) == []

    def test_chunk_texts_returns_flat_list(self) -> None:
        text1 = " ".join([f"a{i}" for i in range(20)])
        text2 = " ".join([f"b{i}" for i in range(20)])
        result = chunk_texts([text1, text2], chunk_size=10, overlap=0)
        # Both texts contribute chunks; result is a flat list of strings
        assert all(isinstance(s, str) for s in result)


# ---------------------------------------------------------------------------
# FetchResult tests
# ---------------------------------------------------------------------------


class TestFetchResult:
    def test_ok_true_for_200(self) -> None:
        fr = FetchResult(url="http://example.com", content="hi", content_type="text/html", status_code=200)
        assert fr.ok is True

    def test_ok_false_for_404(self) -> None:
        fr = FetchResult(
            url="http://example.com", content="", content_type="", status_code=404, error="Not Found"
        )
        assert fr.ok is False

    def test_ok_false_when_error_set(self) -> None:
        fr = FetchResult(url="http://x.com", content="", content_type="", status_code=200, error="timeout")
        assert fr.ok is False

    def test_repr_contains_url_and_status(self) -> None:
        fr = FetchResult(url="http://example.com", content="", content_type="text/html", status_code=200)
        r = repr(fr)
        assert "example.com" in r
        assert "200" in r


# ---------------------------------------------------------------------------
# Pipeline (RAGScraper) tests
# ---------------------------------------------------------------------------


class TestScrapeResult:
    def test_ok_true_when_no_error(self) -> None:
        sr = ScrapeResult(url="http://x.com", chunks=["a"], chunk_count=1)
        assert sr.ok is True

    def test_ok_false_when_error_set(self) -> None:
        sr = ScrapeResult(url="http://x.com", chunks=[], chunk_count=0, error="fail")
        assert sr.ok is False

    def test_repr_includes_url_and_chunk_count(self) -> None:
        sr = ScrapeResult(url="http://x.com", chunks=["a", "b"], chunk_count=2)
        r = repr(sr)
        assert "x.com" in r
        assert "2" in r


class TestRAGScraper:
    def test_scrape_url_with_error_fetch_returns_not_ok(self) -> None:
        """When fetch returns an error FetchResult, scrape_url returns ScrapeResult with ok=False."""
        scraper = RAGScraper()
        error_result = FetchResult(
            url="http://bad.com", content="", content_type="", status_code=0, error="connection refused"
        )
        with patch("KubeAI.scraper.pipeline.fetch", return_value=error_result):
            result = scraper.scrape_url("http://bad.com")
        assert result.ok is False
        assert result.chunk_count == 0
        assert result.error is not None

    def test_scrape_url_with_http_error_returns_not_ok(self) -> None:
        """When fetch returns a 404 FetchResult, scrape_url returns ScrapeResult with ok=False."""
        scraper = RAGScraper()
        error_result = FetchResult(
            url="http://x.com/missing", content="", content_type="", status_code=404, error="Not Found"
        )
        with patch("KubeAI.scraper.pipeline.fetch", return_value=error_result):
            result = scraper.scrape_url("http://x.com/missing")
        assert result.ok is False

    def test_scrape_url_successful_produces_chunks(self) -> None:
        scraper = RAGScraper(chunk_size=5, overlap=0)
        html_body = "<html><body>" + ("word " * 30) + "</body></html>"
        good_result = FetchResult(
            url="http://ok.com", content=html_body, content_type="text/html", status_code=200
        )
        with patch("KubeAI.scraper.pipeline.fetch", return_value=good_result):
            result = scraper.scrape_url("http://ok.com")
        assert result.ok is True
        assert result.chunk_count > 0
        assert len(result.chunks) == result.chunk_count

    def test_load_into_rag_calls_add_documents(self) -> None:
        mock_rag = MagicMock()
        mock_rag.add_documents = MagicMock()
        scraper = RAGScraper()
        results = [
            ScrapeResult(url="http://a.com", chunks=["chunk1", "chunk2"], chunk_count=2),
        ]
        total = scraper.load_into_rag(results, mock_rag)
        mock_rag.add_documents.assert_called_once_with(["chunk1", "chunk2"])
        assert total == 2

    def test_load_into_rag_skips_failed_results(self) -> None:
        mock_rag = MagicMock()
        mock_rag.add_documents = MagicMock()
        scraper = RAGScraper()
        results = [
            ScrapeResult(url="http://good.com", chunks=["c1"], chunk_count=1),
            ScrapeResult(url="http://bad.com", chunks=[], chunk_count=0, error="failed"),
        ]
        total = scraper.load_into_rag(results, mock_rag)
        # add_documents should only be called for the successful result
        assert mock_rag.add_documents.call_count == 1
        assert total == 1

    def test_load_into_rag_returns_zero_on_all_failures(self) -> None:
        mock_rag = MagicMock()
        scraper = RAGScraper()
        results = [
            ScrapeResult(url="http://bad.com", chunks=[], chunk_count=0, error="err"),
        ]
        total = scraper.load_into_rag(results, mock_rag)
        assert total == 0
        mock_rag.add_documents.assert_not_called()

    def test_scrape_and_load_returns_correct_chunk_count(self) -> None:
        mock_rag = MagicMock()
        mock_rag.add_documents = MagicMock()
        scraper = RAGScraper(chunk_size=5, overlap=0)
        html_body = "<html><body>" + ("word " * 30) + "</body></html>"
        good_result = FetchResult(
            url="http://ok.com", content=html_body, content_type="text/html", status_code=200
        )
        with patch("KubeAI.scraper.pipeline.fetch", return_value=good_result):
            total = scraper.scrape_and_load(["http://ok.com"], mock_rag)
        assert total > 0
        mock_rag.add_documents.assert_called_once()

    def test_scrape_urls_returns_list_of_results(self) -> None:
        scraper = RAGScraper()
        error_result = FetchResult(
            url="http://x.com", content="", content_type="", status_code=0, error="err"
        )
        with patch("KubeAI.scraper.pipeline.fetch", return_value=error_result):
            results = scraper.scrape_urls(["http://x.com", "http://y.com"])
        assert len(results) == 2
        assert all(isinstance(r, ScrapeResult) for r in results)

    def test_rag_scraper_repr(self) -> None:
        scraper = RAGScraper(chunk_size=200, overlap=20, timeout=5)
        r = repr(scraper)
        assert "RAGScraper" in r
        assert "200" in r
        assert "20" in r
