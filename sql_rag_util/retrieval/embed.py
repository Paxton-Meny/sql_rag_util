"""Optional embedding retrieval through a developer-supplied function.

The package sends only identifiers, metadata prose, and glossary text to the
function, never cell values. Vectors are cached by schema version.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sql_rag_util.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sql_rag_util.retrieval.cache import JsonCache

__all__ = ["Embedder", "EmbeddingIndex", "build_embedding_index"]

Embedder = "Callable[[Sequence[str]], Sequence[Sequence[float]]]"
_CACHE_NAME = "embeddings"


def _unit(vector: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return tuple(0.0 for _ in vector)
    return tuple(v / norm for v in vector)


@dataclass(frozen=True, slots=True)
class EmbeddingIndex:
    """Unit vectors by document id."""

    ids: tuple[str, ...] = ()
    vectors: tuple[tuple[float, ...], ...] = ()

    def search(self, query_vector: Sequence[float], *, limit: int = 10) -> tuple[tuple[str, float], ...]:
        """Return ``(id, cosine)`` pairs, best first."""
        query = _unit(query_vector)
        scored = []
        for identifier, vector in zip(self.ids, self.vectors, strict=True):
            if len(vector) != len(query):
                raise ConfigurationError("embedding dimension changed; clear the cache or fix the embed function")
            scored.append((identifier, sum(a * b for a, b in zip(query, vector, strict=True))))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return tuple(scored[:limit])

    def to_json(self) -> dict[str, Any]:
        """Return the cache payload."""
        return {"ids": list(self.ids), "vectors": [list(v) for v in self.vectors]}

    @classmethod
    def from_json(cls, payload: object) -> EmbeddingIndex | None:
        """Rebuild from a cache payload, or ``None`` when it is malformed."""
        if not isinstance(payload, dict) or not isinstance(payload.get("ids"), list) or not isinstance(payload.get("vectors"), list):
            return None
        if len(payload["ids"]) != len(payload["vectors"]):
            return None
        return cls(tuple(str(i) for i in payload["ids"]), tuple(tuple(float(x) for x in v) for v in payload["vectors"]))


def build_embedding_index(
    embed: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    documents: Sequence[tuple[str, str]],
    version: str,
    *,
    cache: JsonCache | None = None,
) -> EmbeddingIndex:
    """Embed ``(id, text)`` documents, serving the cache when ``version`` matches."""
    if cache is not None and (payload := cache.load(_CACHE_NAME, version)) is not None:
        cached = EmbeddingIndex.from_json(payload)
        if cached is not None and cached.ids == tuple(i for i, _ in documents):
            return cached
    if not documents:
        return EmbeddingIndex()
    vectors = embed([text for _, text in documents])
    if len(vectors) != len(documents):
        raise ConfigurationError(f"embed returned {len(vectors)} vectors for {len(documents)} texts")
    index = EmbeddingIndex(tuple(i for i, _ in documents), tuple(_unit(v) for v in vectors))
    if cache is not None:
        cache.save(_CACHE_NAME, version, index.to_json())
    return index
