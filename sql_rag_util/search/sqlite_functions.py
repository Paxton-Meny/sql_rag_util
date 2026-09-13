"""Register pure-Python matching functions on a SQLite connection.

This mutates the caller's connection, so it runs only when the developer
calls it. The dialect's function probe then reports the capabilities.
"""

from __future__ import annotations

from sql_rag_util.search.levenshtein import levenshtein
from sql_rag_util.search.soundex import soundex

__all__ = ["register_sqlite_functions"]


def _levenshtein(a: str | None, b: str | None) -> int | None:
    return levenshtein(a, b)


def _soundex_fold(text: str | None) -> str | None:
    return soundex(text)


def register_sqlite_functions(connection: object) -> None:
    """Register ``soundex(text)`` and ``levenshtein(a, b)`` on ``connection``."""
    create = connection.create_function  # type: ignore[attr-defined]
    create("soundex", 1, _soundex_fold, deterministic=True)
    create("levenshtein", 2, _levenshtein, deterministic=True)
