"""Names of optional features a dialect may offer on a given connection."""

from __future__ import annotations

import enum

__all__ = ["Capability"]


class Capability(enum.StrEnum):
    """A feature the query and search layers may use when the dialect reports it."""

    SOUNDEX = "soundex"
    DIFFERENCE = "difference"
    LEVENSHTEIN = "levenshtein"
    TRIGRAM = "trigram"
    FULLTEXT = "fulltext"
    ROW_ESTIMATE = "row_estimate"
    CASE_INSENSITIVE_LIKE = "case_insensitive_like"
