"""Scripted introspection answers for each dialect, derived from the SQLite fixture.

The fixture database is introspected for real, then every statement a
dialect issues while building its catalog is scripted to answer with the
same tables, columns, keys, and foreign keys in that dialect's row shape and
native type names. An engine built on the scripted connection therefore sees
the fixture schema exactly as it would on that database.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sql_rag_util.dialects import load
from sql_rag_util.executor import Executor
from sql_rag_util.schema.introspect import introspect
from sql_rag_util.schema.model import ColumnKind
from sql_rag_util.sql.render import render
from tests.support.fixture import build_fixture
from tests.support.scripted import Rule

if TYPE_CHECKING:
    from sql_rag_util.schema.model import Catalog, TableInfo
    from sql_rag_util.sql.statement import Statement

__all__ = ["DEFAULT_SCHEMAS", "NATIVE_TYPES", "fixture_catalog", "introspection_rules"]

DEFAULT_SCHEMAS = {"postgres": "public", "mysql": "shop", "mssql": "dbo"}
NATIVE_TYPES: dict[str, dict[ColumnKind, str]] = {
    "postgres": {ColumnKind.INTEGER: "integer", ColumnKind.TEXT: "text", ColumnKind.DECIMAL: "numeric", ColumnKind.DATETIME: "timestamp without time zone"},
    "mysql": {ColumnKind.INTEGER: "int", ColumnKind.TEXT: "varchar(255)", ColumnKind.DECIMAL: "decimal(10,2)", ColumnKind.DATETIME: "datetime"},
    "mssql": {ColumnKind.INTEGER: "int", ColumnKind.TEXT: "nvarchar", ColumnKind.DECIMAL: "decimal", ColumnKind.DATETIME: "datetime2"},
}
_ROW_ESTIMATE = 100


def fixture_catalog() -> Catalog:
    """Return the catalog of the SQLite fixture database."""
    connection = build_fixture()
    try:
        return introspect(Executor(connection, "qmark"), load("sqlite"))
    finally:
        connection.close()


def _exactly(statement: Statement, paramstyle: str) -> str:
    return "^" + re.escape(render(statement, paramstyle)[0]) + "$"


def _table(catalog: Catalog, parameters: Any) -> TableInfo:
    values = list(parameters.values()) if isinstance(parameters, dict) else list(parameters)
    return next(t for t in catalog.tables if t.ref.name == values[-1])


def introspection_rules(dialect_name: str, paramstyle: str, *, extensions: tuple[str, ...] = ()) -> list[Rule]:
    """Return rules answering every introspection statement of ``dialect_name`` with the fixture schema.

    Parameters
    ----------
    paramstyle
        The paramstyle the engine will render with, so statement texts match exactly.
    extensions
        Names the capability probe reports, for dialects that have one.
    """
    dialect = load(dialect_name)
    catalog = fixture_catalog()
    schema = DEFAULT_SCHEMAS[dialect_name]
    types = NATIVE_TYPES[dialect_name]

    def columns(_: str, parameters: Any) -> list[tuple[object, ...]]:
        return [(c.name, types[c.kind], c.nullable, c.pk_position) for c in _table(catalog, parameters).columns]

    def foreign_keys(_: str, parameters: Any) -> list[tuple[object, ...]]:
        ref = _table(catalog, parameters).ref
        rows: list[tuple[object, ...]] = []
        for number, fk in enumerate(f for f in catalog.foreign_keys if f.table == ref):
            for position, (column, target) in enumerate(zip(fk.columns, fk.referenced_columns, strict=True), start=1):
                rows.append((f"{ref.name}_fk_{number}", position, column, schema, fk.referenced.name, target))
        return rows

    rules = [
        Rule(_exactly(dialect.tables_statement(None), paramstyle), [(schema, t.ref.name, _ROW_ESTIMATE) for t in catalog.tables]),
        Rule(_exactly(dialect.columns_statement(catalog.tables[0].ref), paramstyle), columns),
        Rule(_exactly(dialect.foreign_keys_statement(catalog.tables[0].ref), paramstyle), foreign_keys),
    ]
    if (default := dialect.default_schema_statement()) is not None:
        rules.append(Rule(_exactly(default, paramstyle), [(schema,)]))
    if (probe := dialect.capability_probe_statement()) is not None:
        rules.append(Rule(_exactly(probe, paramstyle), [(name,) for name in extensions]))
    return rules
