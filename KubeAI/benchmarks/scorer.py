"""Quality scorer — deterministic heuristics, no LLM calls."""

from __future__ import annotations

import re


def _word_set(text: str) -> set[str]:
    """Lowercase word tokens, stripping punctuation."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_output(
    output: str,
    reference: str | None = None,
    criteria: str = "",
) -> float:
    """Score output quality on a 0.0-1.0 scale using deterministic heuristics.

    Priority order:
    1. If *reference* is provided: Jaccard similarity of word sets.
    2. If *criteria* is provided: keyword overlap fraction.
    3. Fallback: length-based score clipped to [0.0, 1.0].

    Args:
        output: The text produced by the adapter.
        reference: Optional reference/gold answer for similarity comparison.
        criteria: Optional space-separated keywords to check for presence.

    Returns:
        A float in [0.0, 1.0].
    """
    if not output:
        return 0.0

    # ── 1. Reference-based: Jaccard similarity ────────────────────────────────
    if reference is not None:
        out_words = _word_set(output)
        ref_words = _word_set(reference)
        if not ref_words:
            return 0.0
        intersection = out_words & ref_words
        union = out_words | ref_words
        if not union:
            return 0.0
        return len(intersection) / len(union)

    # ── 2. Criteria-based: keyword overlap ───────────────────────────────────
    if criteria:
        keywords = _word_set(criteria)
        if not keywords:
            return 0.0
        out_words = _word_set(output)
        matched = sum(1 for kw in keywords if kw in out_words)
        return matched / len(keywords)

    # ── 3. Fallback: length-based score ──────────────────────────────────────
    # 500 characters maps to 1.0; shorter outputs score proportionally less.
    _TARGET_LEN = 500
    score = min(len(output) / _TARGET_LEN, 1.0)
    return score
