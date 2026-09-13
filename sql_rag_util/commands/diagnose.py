"""Suggestions for an empty result, drawn from known values without extra statements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.query.spec import FilterOp
from sql_rag_util.schema.model import TEXT_KINDS
from sql_rag_util.search.levenshtein import levenshtein

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag
    from sql_rag_util.query.spec import Filter
    from sql_rag_util.schema.model import TableInfo

__all__ = ["empty_result_notes"]

_VALUE_OPS = frozenset({FilterOp.EQ, FilterOp.IN, FilterOp.CONTAINS, FilterOp.STARTS_WITH})
_MAX_SUGGESTIONS = 5
_MAX_DISTANCE = 2


def _known_values(engine: SqlRag, table: TableInfo, column: str) -> tuple[str, ...]:
    from sql_rag_util.schema.resolve import agent_name

    entry = engine.retriever.values.for_column(agent_name(engine.catalog, table.ref), column) if engine.retriever_ready else None
    if entry is not None and entry.values:
        return entry.values
    meta = engine.annotated.table_meta.get(table.ref)
    column_meta = meta.column(column) if meta else None
    return column_meta.values if column_meta else ()


def _nearest(wanted: str, known: tuple[str, ...]) -> list[str]:
    folded = wanted.lower()
    scored = []
    for value in known:
        candidate = value.lower()
        if folded == candidate or folded in candidate or candidate.startswith(folded):
            scored.append((0, value))
        else:
            distance = levenshtein(folded, candidate, max_distance=_MAX_DISTANCE)
            if distance is not None and distance <= _MAX_DISTANCE:
                scored.append((distance, value))
    return [v for _, v in sorted(scored)[:_MAX_SUGGESTIONS]]


def empty_result_notes(engine: SqlRag, table: TableInfo, filters: tuple[Filter, ...]) -> tuple[str, ...]:
    """Return one note per text filter whose value does not appear among known values."""
    if not engine.config.diagnose_empty_results:
        return ()
    notes = []
    for flt in filters:
        if flt.op not in _VALUE_OPS or "." in flt.column:
            continue
        column = table.column(flt.column)
        if column is None or column.kind not in TEXT_KINDS:
            continue
        known = _known_values(engine, table, flt.column)
        if not known:
            continue
        wanted = [str(v) for v in (flt.value if isinstance(flt.value, tuple) else (flt.value,))]
        for value in wanted:
            nearest = _nearest(value, known)
            if value in known:
                continue
            if nearest:
                notes.append(f"No {flt.column} equal to {value!r}; nearest known values: {', '.join(nearest)}.")
            else:
                shown = ", ".join(known[:_MAX_SUGGESTIONS]) + (", ..." if len(known) > _MAX_SUGGESTIONS else "")
                notes.append(f"No {flt.column} equal to {value!r}; known values: {shown}.")
    return tuple(notes)
