"""Vectorizer utilities are the indexing-sidecar analogue that build deterministic document embeddings for RAG retrieval."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

import numpy as np

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric terms."""
    if not text:
        return []
    return _TOKEN_PATTERN.findall(text.lower())


def tokens_to_vector(tokens: Iterable[str], dim: int = 256) -> np.ndarray:
    """Build a deterministic hashed term-frequency vector normalized to unit length."""
    vector = np.zeros(dim, dtype=np.float32)
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest, byteorder="little") % dim
        vector[index] += 1.0

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector


def text_to_vector(text: str, dim: int = 256) -> np.ndarray:
    """Build a deterministic normalized vector for one text input."""
    return tokens_to_vector(tokenize(text), dim=dim)


def build_vector_index(docs: Iterable[str], dim: int = 256) -> np.ndarray:
    """Build a dense matrix where each row is a document vector."""
    vectors = [text_to_vector(doc, dim=dim) for doc in docs]
    if not vectors:
        return np.empty((0, dim), dtype=np.float32)
    return np.vstack(vectors)


def cosine_similarity_matrix(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Return cosine similarity between each matrix row and a vector."""
    if matrix.size == 0:
        return np.array([], dtype=np.float32)

    vector_norm = np.linalg.norm(vector)
    row_norms = np.linalg.norm(matrix, axis=1)
    denominator = row_norms * vector_norm

    scores = np.zeros(matrix.shape[0], dtype=np.float32)
    valid = denominator > 0
    if np.any(valid):
        scores[valid] = (matrix[valid] @ vector) / denominator[valid]
    return scores
