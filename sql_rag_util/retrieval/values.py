"""The value index: known values of low-cardinality text columns, for schema linking.

Opt-in through ``project.md``. Never reads sensitive or hidden columns. Each
column costs one bounded statement; the result is cached by catalog and
metadata version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sql_rag_util.retrieval.tokenize import tokenize
from sql_rag_util.schema.model import TEXT_KINDS
from sql_rag_util.schema.resolve import agent_name
from sql_rag_util.search.levenshtein import levenshtein
from sql_rag_util.sql.statement import sql

if TYPE_CHECKING:
    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.executor import Executor
    from sql_rag_util.metadata.annotate import AnnotatedCatalog
    from sql_rag_util.retrieval.cache import JsonCache

__all__ = ["ColumnValues", "ValueHit", "ValueIndex", "build_value_index"]

_CACHE_NAME = "values"
_MIN_FUZZY_LENGTH = 5
_MIN_PREFIX_LENGTH = 4
_MAX_VALUE_CHARS = 80


@dataclass(frozen=True, slots=True)
class ColumnValues:
    """Known values of one column.

    Parameters
    ----------
    complete
        Whether ``values`` holds every distinct value, or only the most frequent samples.
    """

    table: str
    column: str
    values: tuple[str, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class ValueHit:
    """A question word that matched a known value."""

    table: str
    column: str
    value: str
    matched: str
    quality: int


@dataclass(frozen=True, slots=True)
class ValueIndex:
    """Every indexed column."""

    entries: tuple[ColumnValues, ...] = ()

    def for_column(self, table: str, column: str) -> ColumnValues | None:
        """Return the entry for ``table.column``, or ``None``."""
        return next((e for e in self.entries if e.table == table and e.column == column), None)

    def match(self, question: str, *, limit: int = 10) -> tuple[ValueHit, ...]:
        """Return the values that words or phrases of ``question`` refer to, best first."""
        folded = question.lower()
        tokens = tokenize(question)
        hits: dict[tuple[str, str, str], ValueHit] = {}

        def record(entry: ColumnValues, value: str, matched: str, quality: int) -> None:
            key = (entry.table, entry.column, value)
            if key not in hits or hits[key].quality < quality:
                hits[key] = ValueHit(entry.table, entry.column, value, matched, quality)

        for entry in self.entries:
            for value in entry.values:
                value_folded = value.lower()
                if len(value_folded) >= _MIN_PREFIX_LENGTH and " " in value_folded and value_folded in folded:
                    record(entry, value, value, 4)
                    continue
                value_tokens = tokenize(value)
                for token in tokens:
                    if value_tokens and token == value_tokens[0] and len(value_tokens) == 1:
                        record(entry, value, token, 3)
                    elif token == value_folded:
                        record(entry, value, token, 3)
                    elif len(token) >= _MIN_PREFIX_LENGTH and value_folded.startswith(token):
                        record(entry, value, token, 2)
                    elif len(token) >= _MIN_FUZZY_LENGTH and value_tokens and levenshtein(token, value_tokens[0], max_distance=1) == 1:
                        record(entry, value, token, 1)
        ordered = sorted(hits.values(), key=lambda h: (-h.quality, h.table, h.column, h.value))
        return tuple(ordered[:limit])

    def to_json(self) -> list[dict[str, Any]]:
        """Return the cache payload."""
        return [{"table": e.table, "column": e.column, "values": list(e.values), "complete": e.complete} for e in self.entries]

    @classmethod
    def from_json(cls, payload: object) -> ValueIndex:
        """Rebuild from a cache payload; anything malformed yields an empty index."""
        if not isinstance(payload, list):
            return cls()
        entries = []
        for item in payload:
            if isinstance(item, dict) and {"table", "column", "values", "complete"} <= set(item):
                entries.append(ColumnValues(str(item["table"]), str(item["column"]), tuple(str(v) for v in item["values"]), bool(item["complete"])))
        return cls(tuple(entries))


def _column_statement(dialect: Dialect, table_sql: str, column_sql: str, cap: int):  # type: ignore[no-untyped-def]
    body = sql(f"FROM {table_sql} WHERE {column_sql} IS NOT NULL GROUP BY {column_sql} ORDER BY COUNT(*) DESC, {column_sql}")
    return dialect.limited_select(sql(column_sql), body, cap)


def build_value_index(executor: Executor, dialect: Dialect, annotated: AnnotatedCatalog, *, cache: JsonCache | None = None) -> ValueIndex:
    """Read known values for every indexable column, using the cache when its version matches."""
    project = annotated.metadata.project
    if not project.value_index:
        return ValueIndex()
    if cache is not None and (payload := cache.load(_CACHE_NAME, annotated.version)) is not None:
        return ValueIndex.from_json(payload)
    entries = []
    max_distinct, samples = project.value_index_max_distinct, project.samples_per_column
    for table in annotated.catalog.tables:
        table_name = agent_name(annotated.catalog, table.ref)
        for column in annotated.policy.selectable(table.ref, table.columns):
            if column.kind not in TEXT_KINDS:
                continue
            statement = _column_statement(dialect, dialect.qualify(table.ref), dialect.quote(column.name), max_distinct + 1)
            rows = executor.fetch(statement, command="value_index").rows
            values = tuple(str(r[0])[:_MAX_VALUE_CHARS] for r in rows if r and r[0] is not None)
            complete = len(values) <= max_distinct
            entries.append(ColumnValues(table_name, column.name, values if complete else values[:samples], complete))
    index = ValueIndex(tuple(entries))
    if cache is not None:
        cache.save(_CACHE_NAME, annotated.version, index.to_json())
    return index
