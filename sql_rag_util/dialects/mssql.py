"""Microsoft SQL Server dialect."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.dialects.base import Dialect, kind_from_prefixes
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.schema.model import ColumnKind
from sql_rag_util.sql.statement import Statement, bind, join, sql

if TYPE_CHECKING:
    from sql_rag_util.schema.model import TableRef

__all__ = ["MssqlDialect"]

_KINDS: tuple[tuple[str, ColumnKind], ...] = (
    ("bit", ColumnKind.BOOLEAN),
    ("bigint", ColumnKind.INTEGER),
    ("int", ColumnKind.INTEGER),
    ("smallint", ColumnKind.INTEGER),
    ("tinyint", ColumnKind.INTEGER),
    ("decimal", ColumnKind.DECIMAL),
    ("numeric", ColumnKind.DECIMAL),
    ("money", ColumnKind.DECIMAL),
    ("smallmoney", ColumnKind.DECIMAL),
    ("float", ColumnKind.FLOAT),
    ("real", ColumnKind.FLOAT),
    ("datetime", ColumnKind.DATETIME),
    ("smalldatetime", ColumnKind.DATETIME),
    ("date", ColumnKind.DATE),
    ("timestamp", ColumnKind.BINARY),
    ("rowversion", ColumnKind.BINARY),
    ("time", ColumnKind.TIME),
    ("uniqueidentifier", ColumnKind.UUID),
    ("nvarchar", ColumnKind.TEXT),
    ("nchar", ColumnKind.TEXT),
    ("ntext", ColumnKind.TEXT),
    ("varchar", ColumnKind.TEXT),
    ("char", ColumnKind.TEXT),
    ("text", ColumnKind.TEXT),
    ("xml", ColumnKind.TEXT),
    ("varbinary", ColumnKind.BINARY),
    ("binary", ColumnKind.BINARY),
    ("image", ColumnKind.BINARY),
)

_PRIMARY_KEY_POSITION = (
    "(SELECT k.ORDINAL_POSITION FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k "
    "JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc ON tc.CONSTRAINT_NAME = k.CONSTRAINT_NAME "
    "AND tc.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' "
    "AND k.TABLE_SCHEMA = c.TABLE_SCHEMA AND k.TABLE_NAME = c.TABLE_NAME AND k.COLUMN_NAME = c.COLUMN_NAME)"
)
_ROW_ESTIMATE = (
    "(SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = "
    "OBJECT_ID(QUOTENAME(t.TABLE_SCHEMA) + '.' + QUOTENAME(t.TABLE_NAME)) AND p.index_id IN (0, 1))"
)


def _schema_predicate(column: str, schemas: tuple[str, ...] | None) -> Statement:
    if not schemas:
        return sql(f"{column} = SCHEMA_NAME()")
    return sql(f"{column} IN (") + join(", ", (bind(s) for s in schemas)) + sql(")")


class MssqlDialect(Dialect):
    """SQL Server. Identifiers use brackets; limits use a bound ``TOP``."""

    name = "mssql"
    default_paramstyle = "qmark"
    quote_open = "["
    quote_close = "]"
    static_capabilities = frozenset(
        {Capability.SOUNDEX, Capability.DIFFERENCE, Capability.FULLTEXT, Capability.ROW_ESTIMATE}
    )

    def kind_of(self, native_type: str) -> ColumnKind:
        """Classify a ``DATA_TYPE`` value."""
        return kind_from_prefixes(native_type, _KINDS)

    def limited_select(self, select_list: Statement, body: Statement, limit: int) -> Statement:
        """Use ``TOP (?)`` with the limit bound; it needs no ORDER BY, unlike OFFSET FETCH."""
        return sql("SELECT TOP (") + bind(limit) + sql(") ") + select_list + sql(" ") + body

    def soundex_match(self, column_sql: str, text: str) -> Statement:
        """Compare Soundex codes."""
        return sql(f"SOUNDEX({column_sql}) = SOUNDEX(") + bind(text) + sql(")")

    def difference_at_least(self, column_sql: str, text: str, threshold: int) -> Statement:
        """Use the DIFFERENCE score, 0 to 4."""
        return sql(f"DIFFERENCE({column_sql}, ") + bind(text) + sql(") >= ") + bind(threshold)

    def fulltext(self, column_sql: str, text: str) -> Statement:
        """Use FREETEXT, never CONTAINS, because CONTAINS interprets its argument."""
        return sql(f"FREETEXT({column_sql}, ") + bind(text) + sql(")")

    def default_schema_statement(self) -> Statement | None:
        """Return the user's default schema."""
        return sql("SELECT SCHEMA_NAME()")

    def tables_statement(self, schemas: tuple[str, ...] | None) -> Statement:
        """List base tables with a row estimate from the partition catalog."""
        return (
            sql(
                f"SELECT t.TABLE_SCHEMA, t.TABLE_NAME, {_ROW_ESTIMATE} FROM INFORMATION_SCHEMA.TABLES t "
                "WHERE t.TABLE_TYPE = 'BASE TABLE' AND "
            )
            + _schema_predicate("t.TABLE_SCHEMA", schemas)
            + sql(" ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME")
        )

    def columns_statement(self, ref: TableRef) -> Statement:
        """Read columns with nullability as 1 or 0 and the primary key position."""
        return (
            sql(
                "SELECT c.COLUMN_NAME, c.DATA_TYPE, CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END, "
                f"{_PRIMARY_KEY_POSITION} FROM INFORMATION_SCHEMA.COLUMNS c WHERE c.TABLE_SCHEMA = COALESCE("
            )
            + bind(ref.schema)
            + sql(", SCHEMA_NAME()) AND c.TABLE_NAME = ")
            + bind(ref.name)
            + sql(" ORDER BY c.ORDINAL_POSITION")
        )

    def foreign_keys_statement(self, ref: TableRef) -> Statement:
        """Read foreign keys, matching both sides by ordinal position."""
        return (
            sql(
                "SELECT rc.CONSTRAINT_NAME, k.ORDINAL_POSITION, k.COLUMN_NAME, r.TABLE_SCHEMA, r.TABLE_NAME, "
                "r.COLUMN_NAME FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc "
                "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k ON k.CONSTRAINT_NAME = rc.CONSTRAINT_NAME "
                "AND k.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA "
                "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE r ON r.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME "
                "AND r.CONSTRAINT_SCHEMA = rc.UNIQUE_CONSTRAINT_SCHEMA AND r.ORDINAL_POSITION = k.ORDINAL_POSITION "
                "WHERE k.TABLE_SCHEMA = COALESCE("
            )
            + bind(ref.schema)
            + sql(", SCHEMA_NAME()) AND k.TABLE_NAME = ")
            + bind(ref.name)
            + sql(" ORDER BY rc.CONSTRAINT_NAME, k.ORDINAL_POSITION")
        )
