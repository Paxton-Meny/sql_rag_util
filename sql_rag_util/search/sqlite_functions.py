"""Register pure-Python matching functions on a SQLite connection.

The functions are word-aware: a token matches when any word of the column
value matches, so a single full-name column still finds "Jon Smyth" from
"John Smith". This mutates the caller's connection, so it runs only when the
developer calls it; the dialect's function probe then reports the
capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.search.levenshtein import levenshtein
from sql_rag_util.search.soundex import soundex

if TYPE_CHECKING:
    import sqlite3

__all__ = ["register_sqlite_functions", "SOUNDEX_FUNCTION", "LEVENSHTEIN_FUNCTION"]

SOUNDEX_FUNCTION = "sqlrag_soundex_any"
LEVENSHTEIN_FUNCTION = "sqlrag_levenshtein_min"
_UNMATCHED_DISTANCE = 1_000_000


def soundex_any(value: str | None, token: str | None) -> int:
    """Return 1 when any word of ``value`` shares its Soundex code with ``token``."""
    if value is None or token is None:
        return 0
    code = soundex(token)
    if code is None:
        return 0
    return int(any(soundex(word) == code for word in str(value).split()))


def levenshtein_min(value: str | None, token: str | None) -> int:
    """Return the smallest case-folded edit distance between ``token`` and any word of ``value``."""
    if value is None or token is None:
        return _UNMATCHED_DISTANCE
    folded = str(token).lower()
    distances = [levenshtein(word.lower(), folded) or 0 for word in str(value).split()]
    return min(distances) if distances else _UNMATCHED_DISTANCE


def register_sqlite_functions(connection: sqlite3.Connection) -> None:
    """Register the word-aware Soundex and Levenshtein functions on ``connection``."""
    connection.create_function(SOUNDEX_FUNCTION, 2, soundex_any, deterministic=True)
    connection.create_function(LEVENSHTEIN_FUNCTION, 2, levenshtein_min, deterministic=True)
