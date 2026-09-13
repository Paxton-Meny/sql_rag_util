"""BM25 ranking over documents with weighted fields, in pure Python."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sql_rag_util.retrieval.tokenize import tokenize

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Document", "Bm25Index"]

_K1 = 1.2
_B = 0.75


@dataclass(frozen=True, slots=True)
class Document:
    """One ranked unit with named text fields.

    Parameters
    ----------
    id
        Identifier returned in results.
    fields
        Field name to text. Tokenized at index time.
    """

    id: str
    fields: Mapping[str, str] = field(default_factory=dict)


class Bm25Index:
    """A BM25 index where each field contributes term frequency scaled by its weight.

    Parameters
    ----------
    documents
        Documents to index.
    weights
        Field weights; a field not listed weighs 1.0.
    """

    def __init__(self, documents: tuple[Document, ...], weights: Mapping[str, float] | None = None) -> None:
        self._weights = dict(weights or {})
        self._ids = [d.id for d in documents]
        self._term_frequencies: list[Counter[str]] = []
        self._lengths: list[float] = []
        document_frequency: Counter[str] = Counter()
        for document in documents:
            counts: Counter[str] = Counter()
            for name, text in document.fields.items():
                weight = self._weights.get(name, 1.0)
                for token in tokenize(text):
                    counts[token] += weight
            self._term_frequencies.append(counts)
            self._lengths.append(sum(counts.values()))
            document_frequency.update(counts.keys())
        count = len(documents)
        self._average_length = (sum(self._lengths) / count) if count else 0.0
        self._idf = {term: math.log(1 + (count - df + 0.5) / (df + 0.5)) for term, df in document_frequency.items()}

    def __len__(self) -> int:
        return len(self._ids)

    def search(self, query: str, *, limit: int = 10) -> tuple[tuple[str, float], ...]:
        """Return ``(id, score)`` pairs for documents matching ``query``, best first."""
        tokens = tokenize(query)
        if not tokens or not self._ids:
            return ()
        scores: list[tuple[str, float]] = []
        for index, counts in enumerate(self._term_frequencies):
            score = 0.0
            norm = 1 - _B + _B * (self._lengths[index] / self._average_length if self._average_length else 0.0)
            for token in tokens:
                tf = counts.get(token, 0.0)
                if tf:
                    score += self._idf[token] * tf * (_K1 + 1) / (tf + _K1 * norm)
            if score > 0:
                scores.append((self._ids[index], score))
        scores.sort(key=lambda pair: (-pair[1], pair[0]))
        return tuple(scores[:limit])
