"""
Small embedding provider abstraction so Pinecone isn't hardwired to one
embedding implementation. Deliberately minimal — no provider registry, no
retry/fallback framework (that already exists for chat completions in
src/llm/; embeddings don't need a second copy of it for MVP scope).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from src.services.normalization import normalize_whitespace


class EmbeddingProvider(ABC):
    name: str = "unknown"
    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, each of length `dimension`."""


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic, network-free embedding for tests/demo/CI.

    Not a real semantic embedding — it's a stable bag-of-words hash
    projected into a fixed-dimension vector, good enough to make
    local/dev retrieval order deterministic and testable without ever
    calling out to a real embedding API.
    """

    name = "mock"

    def __init__(self, dimension: int = 32) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = normalize_whitespace(text).lower().split()
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = digest[0] % self.dimension
            sign = 1.0 if digest[1] % 2 == 0 else -1.0
            vector[index] += sign
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector
