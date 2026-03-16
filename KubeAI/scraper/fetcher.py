"""Fetcher is the sidecar-proxy analogue: handles raw HTTP ingestion before content enters the RAG pipeline."""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class FetchResult:
    """
    The result of a single HTTP fetch operation.

    Analogous to a sidecar proxy response envelope: carries the raw payload,
    metadata, and any transport-layer error so the pipeline can decide whether
    to process or skip the document.
    """

    url: str
    content: str        # raw HTML or plain text
    content_type: str   # e.g. "text/html"
    status_code: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Return True if the fetch succeeded with a 2xx status and no error."""
        return self.error is None and 200 <= self.status_code < 300

    def __repr__(self) -> str:
        return (
            f"FetchResult(url={self.url!r}, status_code={self.status_code}, "
            f"content_type={self.content_type!r}, ok={self.ok})"
        )


def fetch(
    url: str,
    timeout: int = 10,
    user_agent: str = "KubeAI-Scraper/1.0",
) -> FetchResult:
    """
    Fetch a URL and return a FetchResult. Never raises — errors go into FetchResult.error.

    Uses urllib.request so the scraper has no external dependencies. The
    User-Agent header is set to identify KubeAI traffic. Content type is
    detected from the HTTP response headers; charset is parsed from the
    Content-Type value and used to decode the response body (falls back to
    utf-8 with replacement on unknown or missing charset).

    Args:
        url: The URL to fetch.
        timeout: Connection and read timeout in seconds.
        user_agent: The User-Agent header value sent with the request.

    Returns:
        A FetchResult with the response body, content-type, and status code,
        or a FetchResult with ok=False and error set on any transport failure.
    """
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # type: ignore[arg-type]
            status_code: int = response.status
            raw_content_type: str = response.headers.get("Content-Type", "text/html")
            content_type = raw_content_type.split(";")[0].strip()

            # Detect charset from Content-Type header
            charset = "utf-8"
            for part in raw_content_type.split(";"):
                part = part.strip()
                if part.lower().startswith("charset="):
                    charset = part.split("=", 1)[1].strip().strip('"')
                    break

            raw_bytes: bytes = response.read()
            content = raw_bytes.decode(charset, errors="replace")

    except urllib.error.HTTPError as exc:
        return FetchResult(
            url=url,
            content="",
            content_type="",
            status_code=exc.code,
            error=str(exc),
        )
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        return FetchResult(
            url=url,
            content="",
            content_type="",
            status_code=0,
            error=str(exc),
        )

    return FetchResult(
        url=url,
        content=content,
        content_type=content_type,
        status_code=status_code,
    )
