"""Matching strategies and the predicate that combines them across columns and tokens."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.exceptions import CapabilityError
from sql_rag_util.sql.statement import Statement, bind, join, sql

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sql_rag_util.dialects.base import Dialect

__all__ = ["Strategy", "SearchColumn", "available_strategies", "default_strategies", "search_where"]

DEFAULT_LEVENSHTEIN_DISTANCE = 2
DEFAULT_DIFFERENCE_THRESHOLD = 3
DEFAULT_TRIGRAM_THRESHOLD = 0.3
_MIN_FUZZY_LENGTH = 3


class Strategy(enum.StrEnum):
    """How a token is compared with a column."""

    EXACT = "exact"
    PREFIX = "prefix"
    CONTAINS = "contains"
    SOUNDEX = "soundex"
    DIFFERENCE = "difference"
    LEVENSHTEIN = "levenshtein"
    TRIGRAM = "trigram"
    FULLTEXT = "fulltext"


_REQUIRES: dict[Strategy, str] = {
    Strategy.SOUNDEX: Capability.SOUNDEX,
    Strategy.DIFFERENCE: Capability.DIFFERENCE,
    Strategy.LEVENSHTEIN: Capability.LEVENSHTEIN,
    Strategy.TRIGRAM: Capability.TRIGRAM,
    Strategy.FULLTEXT: Capability.FULLTEXT,
}
_DEFAULT_ORDER = (Strategy.CONTAINS, Strategy.SOUNDEX, Strategy.LEVENSHTEIN, Strategy.TRIGRAM, Strategy.FULLTEXT)


class SearchColumn:
    """A searchable column as rendered SQL plus whether it has a full-text index."""

    __slots__ = ("column_sql", "fulltext", "name")

    def __init__(self, name: str, column_sql: str, *, fulltext: bool = False) -> None:
        self.name = name
        self.column_sql = column_sql
        self.fulltext = fulltext


def available_strategies(capabilities: Iterable[str]) -> tuple[Strategy, ...]:
    """Return every strategy the capabilities allow, in the enumeration order."""
    have = set(capabilities)
    return tuple(s for s in Strategy if s not in _REQUIRES or _REQUIRES[s] in have)


def default_strategies(capabilities: Iterable[str]) -> tuple[Strategy, ...]:
    """Return the strategies used when the agent names none: contains plus the fuzzy ones available."""
    have = set(available_strategies(capabilities))
    return tuple(s for s in _DEFAULT_ORDER if s in have)


def _token_predicate(dialect: Dialect, column: SearchColumn, token: str, strategy: Strategy) -> Statement | None:
    fuzzy_ok = len(token) >= _MIN_FUZZY_LENGTH
    if strategy is Strategy.EXACT:
        return sql(f"{column.column_sql} = ") + bind(token)
    if strategy is Strategy.PREFIX:
        return dialect.starts_with(column.column_sql, token)
    if strategy is Strategy.CONTAINS:
        return dialect.contains(column.column_sql, token)
    if strategy is Strategy.FULLTEXT:
        return dialect.fulltext(column.column_sql, token) if column.fulltext else None
    if not fuzzy_ok:
        return None
    if strategy is Strategy.SOUNDEX:
        return dialect.soundex_match(column.column_sql, token)
    if strategy is Strategy.DIFFERENCE:
        return dialect.difference_at_least(column.column_sql, token, DEFAULT_DIFFERENCE_THRESHOLD)
    if strategy is Strategy.LEVENSHTEIN:
        return dialect.levenshtein_within(column.column_sql, token, DEFAULT_LEVENSHTEIN_DISTANCE)
    return dialect.trigram_at_least(column.column_sql, token, DEFAULT_TRIGRAM_THRESHOLD)


def search_where(
    dialect: Dialect,
    capabilities: Iterable[str],
    columns: tuple[SearchColumn, ...],
    tokens: tuple[str, ...],
    strategies: tuple[Strategy, ...],
    *,
    match_all: bool = True,
) -> Statement:
    """Return the predicate: tokens combined with AND (or OR), each OR-ed across columns and strategies.

    Raises
    ------
    CapabilityError
        When a requested strategy is not available on this connection.
    """
    allowed = set(available_strategies(capabilities))
    missing = [s for s in strategies if s not in allowed]
    if missing:
        raise CapabilityError(f"{dialect.name} cannot use {', '.join(missing)} here", suggestions=tuple(allowed))
    token_clauses = []
    for token in tokens:
        alternatives = [p for c in columns for s in strategies if (p := _token_predicate(dialect, c, token, s)) is not None]
        if not alternatives:
            alternatives = [dialect.contains(c.column_sql, token) for c in columns]
        token_clauses.append(sql("(") + join(" OR ", alternatives) + sql(")"))
    return join(" AND " if match_all else " OR ", token_clauses)
