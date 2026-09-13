"""MySQL and MariaDB dialect."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.dialects.base import Dialect, kind_from_prefixes
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.schema.model import ColumnKind
from sql_rag_util.sql.statement import Statement, bind, join, sql

if TYPE_CHECKING:
    from sql_rag_util.schema.model import TableRef

__all__ = ["MysqlDialect"]

_KINDS: tuple[tuple[str, ColumnKind], ...] = (
    ("tinyint(1)", ColumnKind.BOOLEAN),
    ("bool", ColumnKind.BOOLEAN),
    ("bigint", ColumnKind.INTEGER),
    ("int", ColumnKind.INTEGER),
    ("mediumint", ColumnKind.INTEGER),
    ("smallint", ColumnKind.INTEGER),
    ("tinyint", ColumnKind.INTEGER),
    ("year", ColumnKind.INTEGER),
    ("decimal", ColumnKind.DECIMAL),
    ("numeric", ColumnKind.DECIMAL),
    ("float", ColumnKind.FLOAT),
    ("double", ColumnKind.FLOAT),
    ("real", ColumnKind.FLOAT),
    ("datetime", ColumnKind.DATETIME),
    ("timestamp", ColumnKind.DATETIME),
    ("date", ColumnKind.DATE),
    ("time", ColumnKind.TIME),
    ("json", ColumnKind.JSON),
    ("char", ColumnKind.TEXT),
    ("varchar", ColumnKind.TEXT),
    ("tinytext", ColumnKind.TEXT),
    ("mediumtext", ColumnKind.TEXT),
    ("longtext", ColumnKind.TEXT),
    ("text", ColumnKind.TEXT),
    ("enum", ColumnKind.TEXT),
    ("set", ColumnKind.TEXT),
    ("tinyblob", ColumnKind.BINARY),
    ("mediumblob", ColumnKind.BINARY),
    ("longblob", ColumnKind.BINARY),
    ("blob", ColumnKind.BINARY),
    ("varbinary", ColumnKind.BINARY),
    ("binary", ColumnKind.BINARY),
    ("bit", ColumnKind.BINARY),
)

_PRIMARY_KEY_POSITION = (
    "(SELECT k.ORDINAL_POSITION FROM information_schema.KEY_COLUMN_USAGE k "
    "WHERE k.CONSTRAINT_NAME = 'PRIMARY' AND k.TABLE_SCHEMA = c.TABLE_SCHEMA "
    "AND k.TABLE_NAME = c.TABLE_NAME AND k.COLUMN_NAME = c.COLUMN_NAME)"
)


def _schema_predicate(column: str, schemas: tuple[str, ...] | None) -> Statement:
    if not schemas:
        return sql(f"{column} = DATABASE()")
    return sql(f"{column} IN (") + join(", ", (bind(s) for s in schemas)) + sql(")")


class MysqlDialect(Dialect):
    """MySQL and MariaDB. The namespace is the database; ``DATABASE()`` is the default."""

    name = "mysql"
    default_paramstyle = "format"
    quote_open = "`"
    quote_close = "`"
    static_capabilities = frozenset(
        {Capability.SOUNDEX, Capability.CASE_INSENSITIVE_LIKE, Capability.ROW_ESTIMATE}
    )

    def kind_of(self, native_type: str) -> ColumnKind:
        """Classify a ``COLUMN_TYPE`` value such as ``tinyint(1)`` or ``varchar(80)``."""
        return kind_from_prefixes(native_type, _KINDS)

    def soundex_match(self, column_sql: str, text: str) -> Statement:
        """Compare Soundex codes."""
        return sql(f"SOUNDEX({column_sql}) = SOUNDEX(") + bind(text) + sql(")")

    def default_schema_statement(self) -> Statement | None:
        """Return the current database name."""
        return sql("SELECT DATABASE()")

    def tables_statement(self, schemas: tuple[str, ...] | None) -> Statement:
        """List base tables with the catalog's row estimate."""
        return (
            sql(
                "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES "
                "WHERE TABLE_TYPE = 'BASE TABLE' AND "
            )
            + _schema_predicate("TABLE_SCHEMA", schemas)
            + sql(" ORDER BY TABLE_SCHEMA, TABLE_NAME")
        )

    def columns_statement(self, ref: TableRef) -> Statement:
        """Read columns with their full type text and primary key position."""
        return (
            sql(
                "SELECT c.COLUMN_NAME, c.COLUMN_TYPE, c.IS_NULLABLE = 'YES', "
                f"{_PRIMARY_KEY_POSITION} FROM information_schema.COLUMNS c "
                "WHERE c.TABLE_SCHEMA = COALESCE("
            )
            + bind(ref.schema)
            + sql(", DATABASE()) AND c.TABLE_NAME = ")
            + bind(ref.name)
            + sql(" ORDER BY c.ORDINAL_POSITION")
        )

    def foreign_keys_statement(self, ref: TableRef) -> Statement:
        """Read foreign keys; the referenced column is on the same row."""
        return (
            sql(
                "SELECT CONSTRAINT_NAME, ORDINAL_POSITION, COLUMN_NAME, REFERENCED_TABLE_SCHEMA, "
                "REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = COALESCE("
            )
            + bind(ref.schema)
            + sql(", DATABASE()) AND TABLE_NAME = ")
            + bind(ref.name)
            + sql(" AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION")
        )
