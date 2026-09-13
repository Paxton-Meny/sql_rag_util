"""Build a :class:`~sql_rag_util.schema.model.Catalog` from a live connection."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import IntrospectionError
from sql_rag_util.schema.model import Catalog, ColumnInfo, ForeignKeyInfo, TableInfo, TableRef
from sql_rag_util.schema.relationships import derive_relationships

if TYPE_CHECKING:
    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.executor import Executor

__all__ = ["introspect", "fingerprint_of"]

_COMMAND = "introspect"
_FINGERPRINT_LENGTH = 16


def _scalar(executor: Executor, dialect: Dialect) -> str | None:
    statement = dialect.default_schema_statement()
    if statement is None:
        return None
    rows = executor.fetch(statement, command=_COMMAND).rows
    value = rows[0][0] if rows and rows[0] else None
    return str(value) if value is not None else None


def _normalize_schema(schema: object, default: str | None, explicit: bool) -> str | None:
    if schema is None:
        return None
    text = str(schema)
    if not explicit and text == default:
        return None
    return text


def _columns(executor: Executor, dialect: Dialect, ref: TableRef) -> tuple[ColumnInfo, ...]:
    rows = executor.fetch(dialect.columns_statement(ref), command=_COMMAND).rows
    if not rows:
        raise IntrospectionError(f"table {ref.qualified} reported no columns")
    return tuple(
        ColumnInfo(str(name), str(native or ""), dialect.kind_of(str(native or "")), bool(nullable), int(pk) if pk else None)
        for name, native, nullable, pk in rows
    )


def _foreign_keys(
    executor: Executor, dialect: Dialect, table: TableInfo, tables: dict[TableRef, TableInfo], default: str | None, explicit: bool
) -> tuple[ForeignKeyInfo, ...]:
    rows = executor.fetch(dialect.foreign_keys_statement(table.ref), command=_COMMAND).rows
    grouped: dict[object, list[tuple[object, ...]]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)
    out: list[ForeignKeyInfo] = []
    for constraint, members in grouped.items():
        members.sort(key=lambda r: int(r[1]))
        first = members[0]
        ref_schema = _normalize_schema(first[3], default, explicit)
        referenced = TableRef(ref_schema if ref_schema is not None else table.ref.schema, str(first[4]))
        target = tables.get(referenced)
        if target is None:
            continue
        columns = tuple(str(m[2]) for m in members)
        referenced_columns = tuple(
            str(m[5]) if m[5] is not None else _implied_key(target, i, referenced) for i, m in enumerate(members)
        )
        name = str(constraint) if isinstance(constraint, str) else None
        out.append(ForeignKeyInfo(table.ref, columns, referenced, referenced_columns, name))
    return tuple(out)


def _implied_key(target: TableInfo, position: int, referenced: TableRef) -> str:
    key = target.primary_key
    if position >= len(key):
        raise IntrospectionError(f"foreign key to {referenced.qualified} implies a primary key column it lacks")
    return key[position]


def fingerprint_of(tables: tuple[TableInfo, ...], foreign_keys: tuple[ForeignKeyInfo, ...]) -> str:
    """Return a stable hash of structure only, ignoring row estimates."""
    payload = [
        [t.ref.schema, t.ref.name, [[c.name, c.native_type, c.nullable, c.pk_position] for c in t.columns]]
        for t in tables
    ] + [[f.table.qualified, list(f.columns), f.referenced.qualified, list(f.referenced_columns)] for f in foreign_keys]
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return digest[:_FINGERPRINT_LENGTH]


def introspect(
    executor: Executor,
    dialect: Dialect,
    *,
    schemas: tuple[str, ...] | None = None,
    include_row_estimates: bool = True,
) -> Catalog:
    """Read tables, columns, keys, and capabilities into a catalog.

    Parameters
    ----------
    executor
        Executor bound to the connection.
    dialect
        The dialect of that connection.
    schemas
        Namespaces to load, or ``None`` for the dialect's default only. When
        ``None``, tables carry no schema in their refs.
    include_row_estimates
        Whether to keep the catalog's row estimates.
    """
    explicit = bool(schemas)
    default = _scalar(executor, dialect) if not explicit else None
    listed = executor.fetch(dialect.tables_statement(schemas), command=_COMMAND).rows
    tables: dict[TableRef, TableInfo] = {}
    for schema, name, estimate in listed:
        ref = TableRef(_normalize_schema(schema, default, explicit), str(name))
        rows = int(estimate) if include_row_estimates and estimate is not None and int(estimate) >= 0 else None
        tables[ref] = TableInfo(ref, _columns(executor, dialect, ref), rows)
    foreign_keys: list[ForeignKeyInfo] = []
    for table in tables.values():
        foreign_keys.extend(_foreign_keys(executor, dialect, table, tables, default, explicit))
    capabilities = set(dialect.static_capabilities)
    probe = dialect.capability_probe_statement()
    if probe is not None:
        names = [str(r[0]) for r in executor.fetch(probe, command=_COMMAND).rows if r and r[0] is not None]
        capabilities |= dialect.probe_capabilities(names)
    table_tuple = tuple(tables.values())
    fk_tuple = tuple(foreign_keys)
    return Catalog(
        dialect.name,
        table_tuple,
        fk_tuple,
        derive_relationships(fk_tuple),
        frozenset(capabilities),
        fingerprint_of(table_tuple, fk_tuple),
    )
