"""Resolve agent-supplied names against the catalog.

Resolution is exact first, then a unique case-insensitive match, and
otherwise an error carrying close matches so the agent can correct itself.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import UnknownColumnError, UnknownRelationshipError, UnknownTableError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from sql_rag_util.schema.model import Catalog, ColumnInfo, Relationship, TableInfo, TableRef

__all__ = ["agent_name", "resolve_table", "resolve_column", "resolve_relationship", "closest"]

_SUGGESTION_COUNT = 3
_SUGGESTION_CUTOFF = 0.5


def closest(name: str, candidates: Iterable[str]) -> tuple[str, ...]:
    """Return up to three candidates that look like ``name``."""
    pool = list(candidates)
    matches = difflib.get_close_matches(name, pool, n=_SUGGESTION_COUNT, cutoff=_SUGGESTION_CUTOFF)
    lowered = difflib.get_close_matches(name.lower(), [c.lower() for c in pool], n=_SUGGESTION_COUNT, cutoff=_SUGGESTION_CUTOFF)
    by_lower = {c.lower(): c for c in pool}
    ordered = list(matches) + [by_lower[m] for m in lowered if by_lower[m] not in matches]
    return tuple(ordered[:_SUGGESTION_COUNT])


def agent_name(catalog: Catalog, ref: TableRef) -> str:
    """Return the shortest unambiguous name for ``ref``: bare when unique, else qualified."""
    same = [t for t in catalog.tables if t.ref.name == ref.name]
    return ref.name if len(same) == 1 else ref.qualified


def _pick(name: str, items: Iterable[tuple[str, object]], error: Callable[[str, tuple[str, ...]], Exception], what: str) -> object:
    pairs = list(items)
    for key, item in pairs:
        if key == name:
            return item
    folded = [item for key, item in pairs if key.lower() == name.lower()]
    if len(folded) == 1:
        return folded[0]
    suggestions = closest(name, (key for key, _ in pairs))
    hint = f"; did you mean {', '.join(suggestions)}?" if suggestions else ""
    raise error(f"unknown {what} {name!r}{hint}", suggestions)


def resolve_table(catalog: Catalog, name: str) -> TableInfo:
    """Return the table called ``name``, accepting bare or ``schema.name`` forms."""
    items = [(agent_name(catalog, t.ref), t) for t in catalog.tables]
    items += [(t.ref.qualified, t) for t in catalog.tables if t.ref.schema]
    return _pick(name, items, lambda m, s: UnknownTableError(m, suggestions=s), "table")  # type: ignore[return-value]


def resolve_column(table: TableInfo, name: str) -> ColumnInfo:
    """Return the column of ``table`` called ``name``."""
    items = [(c.name, c) for c in table.columns]
    return _pick(name, items, lambda m, s: UnknownColumnError(f"{m} on table {table.ref.qualified}", suggestions=s), "column")  # type: ignore[return-value]


def resolve_relationship(catalog: Catalog, table: TableInfo, name: str) -> Relationship:
    """Return the relationship navigated from ``table`` called ``name``."""
    items = [(r.name, r) for r in catalog.relationships_of(table.ref)]
    return _pick(name, items, lambda m, s: UnknownRelationshipError(f"{m} on table {table.ref.qualified}", suggestions=s), "relationship")  # type: ignore[return-value]
