"""Extractor is the init-container analogue: strips markup noise from raw HTML before content is indexed."""

from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser


# Tags whose content should be skipped entirely (including nested content)
_SKIP_TAGS: frozenset[str] = frozenset(
    {"script", "style", "head", "noscript", "nav", "footer", "aside"}
)


class _TextExtractor(HTMLParser):
    """
    HTMLParser subclass that collects visible text from an HTML document.

    Content inside noise tags (script, style, head, noscript, nav, footer,
    aside) is discarded. All other text is accumulated and normalised.
    """

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth: int = 0   # nesting counter for skipped tags
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        """Return the accumulated, normalised visible text."""
        raw = " ".join(self._parts)
        # Collapse runs of whitespace (spaces, tabs, newlines) to a single space
        normalised = re.sub(r"[ \t\r\n]+", " ", raw)
        return normalised.strip()


class _LinkExtractor(HTMLParser):
    """HTMLParser subclass that collects all href attribute values from <a> tags."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for attr_name, attr_value in attrs:
            if attr_name.lower() == "href" and attr_value:
                absolute = urllib.parse.urljoin(self._base_url, attr_value)
                self.links.append(absolute)


def extract_text(html: str) -> str:
    """
    Extract visible text from HTML, stripping tags and noise elements.

    Content inside script, style, head, noscript, nav, footer, and aside
    tags is discarded. Remaining text is whitespace-normalised and returned
    as a single string.

    Args:
        html: Raw HTML source to process.

    Returns:
        A single normalised string of visible text.
    """
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


def extract_links(html: str, base_url: str = "") -> list[str]:
    """
    Extract absolute href links from HTML.

    Uses urllib.parse.urljoin to resolve relative URLs against base_url.
    Only href attributes on <a> tags are returned; fragment-only links and
    javascript: hrefs are included as-is (callers should filter as needed).

    Args:
        html: Raw HTML source to parse.
        base_url: Base URL used to resolve relative links. Defaults to "".

    Returns:
        A list of absolute URL strings in document order.
    """
    parser = _LinkExtractor(base_url)
    parser.feed(html)
    return parser.links
