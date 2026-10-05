"""Configuration and limits for a :class:`~sql_rag_util.engine.SqlRag` instance."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = ["Limits", "Config", "StatementEvent"]


@dataclass(frozen=True, slots=True)
class Limits:
    """Caps applied to every statement and every result.

    Every value must be a positive integer, and ``max_rows`` may not exceed
    ``hard_max_rows``. An agent may request fewer rows than ``max_rows`` and
    never more than ``hard_max_rows``.
    """

    max_rows: int = 50
    hard_max_rows: int = 500
    max_cell_chars: int = 200
    max_columns: int = 30
    max_in_values: int = 100
    max_filters: int = 10
    max_group_by: int = 2
    max_measures: int = 5
    max_join_depth: int = 2
    max_search_tokens: int = 5
    context_budget_tokens: int = 1500

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ConfigurationError(f"Limits.{f.name} must be a positive integer, got {value!r}")
        if self.max_rows > self.hard_max_rows:
            raise ConfigurationError(
                f"Limits.max_rows ({self.max_rows}) exceeds hard_max_rows ({self.hard_max_rows})"
            )


@dataclass(frozen=True, slots=True)
class StatementEvent:
    """What the audit hook receives after every executed statement.

    Parameters
    ----------
    command
        Name of the command that produced the statement.
    sql
        The rendered statement text.
    parameter_count
        How many values were bound. Values themselves are not included.
    elapsed_seconds
        Wall-clock time spent in the driver.
    row_count
        Rows returned to the command, after the extra row fetched to detect
        truncation was dropped.
    """

    command: str
    sql: str
    parameter_count: int
    elapsed_seconds: float
    row_count: int


@dataclass(frozen=True, slots=True)
class Config:
    """Behavior switches for an engine.

    Parameters
    ----------
    limits
        Caps applied to statements and results.
    allow_metadata_writes
        Whether the toolkit's editing commands are exposed and permitted.
    diagnose_empty_results
        Whether an empty result triggers bounded suggestion lookups.
    reveal_sql
        Whether envelopes include the rendered statement, for developers. The
        statement shows scope predicates, hidden columns included, to whoever
        reads the envelope, so it stays off wherever an agent is served.
    include_row_estimates
        Whether introspection keeps the row estimates the catalog reports.
        The table listing statement runs either way.
    scope
        Developer predicate source: given a table's qualified name, returns
        filter mappings applied to every statement on that table. Scope
        filters are trusted: they may name hidden and sensitive columns,
        including through relationship paths, and the agent never sees them.
        Their values must come from the application, such as the signed-in
        tenant, and never from anything the agent supplied.
    on_statement
        Audit hook called after every executed statement.
    embed
        Optional function from texts to vectors for schema retrieval. It
        receives the question text and, per table, identifiers of visible
        columns and the text written in metadata; never values read from the
        database. ``docs/threat-model.md`` lists every field.
    """

    limits: Limits = Limits()
    allow_metadata_writes: bool = False
    diagnose_empty_results: bool = True
    reveal_sql: bool = False
    include_row_estimates: bool = True
    scope: Callable[[str], tuple[dict[str, object], ...]] | None = None
    on_statement: Callable[[StatementEvent], None] | None = None
    embed: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None = None

    def __post_init__(self) -> None:
        if self.scope is not None and not callable(self.scope):
            raise ConfigurationError("Config.scope must be callable or None")
        if self.on_statement is not None and not callable(self.on_statement):
            raise ConfigurationError("Config.on_statement must be callable or None")
        if self.embed is not None and not callable(self.embed):
            raise ConfigurationError("Config.embed must be callable or None")
