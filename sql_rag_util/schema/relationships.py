"""Derive navigable relationships from foreign keys.

Every foreign key yields a forward ``to_one`` relationship named after the
referenced table and a reverse ``to_many`` relationship named after the
referencing table. When two keys on one table would share a name, both use
the ``<table>_via_<column>`` form so neither is ambiguous.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from sql_rag_util.schema.model import Relationship

if TYPE_CHECKING:
    from sql_rag_util.schema.model import ForeignKeyInfo, TableRef

__all__ = ["derive_relationships"]


def _via(columns: tuple[str, ...]) -> str:
    return "_".join(columns)


def _candidates(fk: ForeignKeyInfo) -> tuple[tuple[TableRef, str, str, str], ...]:
    forward = (fk.table, fk.referenced.name, f"{fk.referenced.name}_via_{_via(fk.columns)}", "to_one")
    reverse = (fk.referenced, fk.table.name, f"{fk.table.name}_via_{_via(fk.columns)}", "to_many")
    return forward, reverse


def derive_relationships(foreign_keys: tuple[ForeignKeyInfo, ...]) -> tuple[Relationship, ...]:
    """Return forward and reverse relationships for every foreign key.

    Parameters
    ----------
    foreign_keys
        Constraints whose tables are all present in the catalog.
    """
    base_counts: Counter[tuple[TableRef, str]] = Counter()
    for fk in foreign_keys:
        for source, base, _, _ in _candidates(fk):
            base_counts[(source, base)] += 1
    chosen: Counter[tuple[TableRef, str]] = Counter()
    out: list[Relationship] = []
    for fk in foreign_keys:
        forward, reverse = _candidates(fk)
        for source, base, via, cardinality in (forward, reverse):
            name = base if base_counts[(source, base)] == 1 else via
            if chosen[(source, name)]:
                name = f"{name}_{cardinality}"
            chosen[(source, name)] += 1
            if cardinality == "to_one":
                target, pairs = fk.referenced, tuple(zip(fk.columns, fk.referenced_columns, strict=True))
            else:
                target, pairs = fk.table, tuple(zip(fk.referenced_columns, fk.columns, strict=True))
            out.append(Relationship(name, source, target, pairs, cardinality, "foreign_key"))  # type: ignore[arg-type]
    return tuple(out)
