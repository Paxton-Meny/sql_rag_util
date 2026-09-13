"""SQLite dialect."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.dialects.base import Dialect
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.schema.model import ColumnKind
from sql_rag_util.sql.statement import Statement, bind, sql

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sql_rag_util.schema.model import TableRef

__all__ = ["SqliteDialect", "MINIMUM_SQLITE_VERSION"]

MINIMUM_SQLITE_VERSION = (3, 30, 0)

_DECLARED_KINDS: tuple[tuple[str, ColumnKind], ...] = (
    ("bool", ColumnKind.BOOLEAN),
    ("datetime", ColumnKind.DATETIME),
    ("timestamp", ColumnKind.DATETIME),
    ("date", ColumnKind.DATE),
    ("time", ColumnKind.TIME),
    ("json", ColumnKind.JSON),
    ("uuid", ColumnKind.UUID),
    ("decimal", ColumnKind.DECIMAL),
    ("numeric", ColumnKind.DECIMAL),
)
_AFFINITY_KINDS: tuple[tuple[str, ColumnKind], ...] = (
    ("int", ColumnKind.INTEGER),
    ("char", ColumnKind.TEXT),
    ("clob", ColumnKind.TEXT),
    ("text", ColumnKind.TEXT),
    ("blob", ColumnKind.BINARY),
    ("real", ColumnKind.FLOAT),
    ("floa", ColumnKind.FLOAT),
    ("doub", ColumnKind.FLOAT),
)
_PROBED_FUNCTIONS: dict[str, str] = {
    "soundex": Capability.SOUNDEX,
    "levenshtein": Capability.LEVENSHTEIN,
}


class SqliteDialect(Dialect):
    """SQLite through the standard library ``sqlite3`` module or a compatible driver.

    Introspection uses the table-valued ``pragma_*`` functions so that the
    table name is bound, which needs SQLite 3.16 or newer; the function
    list probe needs 3.30, which is the floor this dialect declares.
    """

    name = "sqlite"
    default_paramstyle = "qmark"
    static_capabilities = frozenset({Capability.CASE_INSENSITIVE_LIKE})

    def kind_of(self, native_type: str) -> ColumnKind:
        """Classify by declared type first, then by the documented affinity rules."""
        folded = native_type.strip().lower()
        if not folded:
            return ColumnKind.BINARY
        for prefix, kind in _DECLARED_KINDS:
            if folded.startswith(prefix):
                return kind
        for fragment, kind in _AFFINITY_KINDS:
            if fragment in folded:
                return kind
        return ColumnKind.DECIMAL

    def tables_statement(self, schemas: tuple[str, ...] | None) -> Statement:
        """List ordinary tables; SQLite has one namespace so ``schemas`` is ignored."""
        return sql(
            "SELECT NULL, name, NULL FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite!_%' ESCAPE '!' ORDER BY name"
        )

    def columns_statement(self, ref: TableRef) -> Statement:
        """Read columns, including generated ones, with the table name bound."""
        return (
            sql(
                'SELECT name, type, "notnull" = 0, CASE WHEN pk = 0 THEN NULL ELSE pk END '
                "FROM pragma_table_xinfo("
            )
            + bind(ref.name)
            + sql(") WHERE hidden IN (0, 2, 3) ORDER BY cid")
        )

    def foreign_keys_statement(self, ref: TableRef) -> Statement:
        """Read foreign keys; ``to`` is NULL when the parent primary key is implied."""
        return (
            sql('SELECT id, seq, "from", NULL, "table", "to" FROM pragma_foreign_key_list(')
            + bind(ref.name)
            + sql(") ORDER BY id, seq")
        )

    def soundex_match(self, column_sql: str, text: str) -> Statement:
        """Compare Soundex codes through the registered or built-in function."""
        return sql(f"soundex({column_sql}) = soundex(") + bind(text) + sql(")")

    def levenshtein_within(self, column_sql: str, text: str, distance: int) -> Statement:
        """Use the registered ``levenshtein`` function."""
        return sql(f"levenshtein({column_sql}, ") + bind(text) + sql(") <= ") + bind(distance)

    def capability_probe_statement(self) -> Statement | None:
        """Report which registered functions exist, so registration is detected rather than assumed."""
        return sql("SELECT name FROM pragma_function_list WHERE name IN ('soundex', 'levenshtein')")

    def probe_capabilities(self, names: Iterable[str]) -> frozenset[str]:
        """Map registered function names to capabilities."""
        return frozenset(_PROBED_FUNCTIONS[n.lower()] for n in names if n.lower() in _PROBED_FUNCTIONS)
