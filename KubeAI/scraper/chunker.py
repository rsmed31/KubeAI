"""Chunker is the resource-limit analogue: breaks long text into bounded segments so no single document overwhelms context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    """
    A bounded segment of text produced by chunk_text.

    Analogous to a resource-limited container slice: each Chunk carries its
    content, its position within the original source (by index and character
    offsets), and enough metadata for downstream retrieval systems to
    reconstruct provenance.
    """

    text: str
    index: int          # chunk index within the source text
    char_start: int     # best-effort character offset in the original text
    char_end: int       # best-effort character offset (exclusive)

    def __repr__(self) -> str:
        preview = self.text[:40].replace("\n", " ")
        return (
            f"Chunk(index={self.index}, char_start={self.char_start}, "
            f"char_end={self.char_end}, text={preview!r})"
        )


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """
    Split text into overlapping word-based chunks.

    The algorithm:
    1. Splits text into words using str.split() (handles all whitespace).
    2. Slides a window of chunk_size words with a step of (chunk_size - overlap).
    3. Joins each window back into a string with single spaces.
    4. Records best-effort char_start / char_end offsets by searching for the
       first word of each chunk in the original text from the previous chunk's
       end position.

    Args:
        text: The text to chunk.
        chunk_size: Target number of words per chunk (window size).
        overlap: Number of words shared between adjacent chunks.
                 Must be less than chunk_size.

    Returns:
        A list of Chunk objects. Returns an empty list for empty input.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if not words:
        return []

    # Clamp overlap to avoid infinite loops
    effective_overlap = max(0, min(overlap, chunk_size - 1))
    step = chunk_size - effective_overlap
    if step <= 0:
        step = 1

    chunks: list[Chunk] = []
    search_from = 0  # character position in original text to search from

    for idx, start_word in enumerate(range(0, len(words), step)):
        window = words[start_word: start_word + chunk_size]
        if not window:
            break
        chunk_str = " ".join(window)

        # Best-effort: find where this chunk starts in the original text
        first_word = window[0]
        found = text.find(first_word, search_from)
        if found == -1:
            # Fallback: scan from the very beginning
            found = text.find(first_word, 0)
        char_start = found if found != -1 else search_from
        char_end = char_start + len(chunk_str)
        # Advance search position to just after the first word so next chunk
        # can overlap correctly
        search_from = char_start + len(first_word)

        chunks.append(
            Chunk(
                text=chunk_str,
                index=idx,
                char_start=char_start,
                char_end=char_end,
            )
        )

    return chunks


def chunk_texts(
    texts: list[str],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """
    Chunk multiple texts and return a flat list of chunk strings.

    Convenience wrapper over chunk_text that processes each text independently
    and concatenates the resulting chunk strings.

    Args:
        texts: A list of text strings to chunk.
        chunk_size: Target words per chunk.
        overlap: Overlap words between consecutive chunks.

    Returns:
        A flat list of chunk text strings from all input texts.
    """
    result: list[str] = []
    for text in texts:
        result.extend(c.text for c in chunk_text(text, chunk_size, overlap))
    return result
