"""Reciprocal rank fusion of several rankings, without score normalization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["reciprocal_rank_fusion"]

_K = 60.0


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], *, weights: Sequence[float] | None = None) -> tuple[tuple[str, float], ...]:
    """Fuse ordered id lists; an id's score is the weighted sum of ``1 / (k + rank)`` over rankings."""
    factors = list(weights) if weights is not None else [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, factors, strict=True):
        for position, identifier in enumerate(ranking, 1):
            scores[identifier] = scores.get(identifier, 0.0) + weight / (_K + position)
    return tuple(sorted(scores.items(), key=lambda pair: (-pair[1], pair[0])))
