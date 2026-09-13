"""PostgreSQL dialect."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.dialects.base import LIKE_ESCAPE, Dialect, escape_like, kind_from_prefixes
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.schema.model import ColumnKind
from sql_rag_util.sql.statement import Statement, bind, join, sql

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sql_rag_util.schema.model import TableRef

__all__ = ["PostgresDialect"]

_KINDS: tuple[tuple[str, ColumnKind], ...] = (
    ("bool", ColumnKind.BOOLEAN),
    ("interval", ColumnKind.OTHER),
    ("bigint", ColumnKind.INTEGER),
    ("integer", ColumnKind.INTEGER),
    ("smallint", ColumnKind.INTEGER),
    ("int", ColumnKind.INTEGER),
    ("numeric", ColumnKind.DECIMAL),
    ("decimal", ColumnKind.DECIMAL),
    ("money", ColumnKind.DECIMAL),
    ("double", ColumnKind.FLOAT),
    ("real", ColumnKind.FLOAT),
    ("float", ColumnKind.FLOAT),
    ("timestamp", ColumnKind.DATETIME),
    ("date", ColumnKind.DATE),
    ("time", ColumnKind.TIME),
    ("uuid", ColumnKind.UUID),
    ("json", ColumnKind.JSON),
    ("character", ColumnKind.TEXT),
    ("varchar", ColumnKind.TEXT),
    ("text", ColumnKind.TEXT),
    ("citext", ColumnKind.TEXT),
    ("name", ColumnKind.TEXT),
    ("bytea", ColumnKind.BINARY),
)
_EXTENSION_CAPABILITIES: dict[str, frozenset[str]] = {
    "pg_trgm": frozenset({Capability.TRIGRAM}),
    "fuzzystrmatch": frozenset({Capability.LEVENSHTEIN, Capability.SOUNDEX, Capability.DIFFERENCE}),
}
_PRIMARY_KEY_POSITION = (
    "(SELECT k.ordinal_position FROM information_schema.table_constraints tc "
    "JOIN information_schema.key_column_usage k ON k.constraint_name = tc.constraint_name "
    "AND k.constraint_schema = tc.constraint_schema WHERE tc.constraint_type = 'PRIMARY KEY' "
    "AND tc.table_schema = c.table_schema AND tc.table_name = c.table_name AND k.column_name = c.column_name)"
)
_ROW_ESTIMATE = (
    "(SELECT CAST(pc.reltuples AS bigint) FROM pg_catalog.pg_class pc "
    "JOIN pg_catalog.pg_namespace pn ON pn.oid = pc.relnamespace "
    "WHERE pn.nspname = t.table_schema AND pc.relname = t.table_name)"
)


def _schema_predicate(column: str, schemas: tuple[str, ...] | None) -> Statement:
    if not schemas:
        return sql(f"{column} = current_schema()")
    return sql(f"{column} IN (") + join(", ", (bind(s) for s in schemas)) + sql(")")


class PostgresDialect(Dialect):
    """PostgreSQL. Substring matches use ``ILIKE``; fuzzy features come from extensions."""

    name = "postgres"
    default_paramstyle = "format"
    static_capabilities = frozenset({Capability.CASE_INSENSITIVE_LIKE, Capability.ROW_ESTIMATE})

    def kind_of(self, native_type: str) -> ColumnKind:
        """Classify a ``data_type`` or, for user-defined types, a ``udt_name``."""
        return kind_from_prefixes(native_type, _KINDS)

    def contains(self, column_sql: str, text: str) -> Statement:
        """Case-insensitive substring match through ``ILIKE``."""
        return sql(f"{column_sql} ILIKE ") + bind(f"%{escape_like(text)}%") + sql(f" ESCAPE '{LIKE_ESCAPE}'")

    def starts_with(self, column_sql: str, text: str) -> Statement:
        """Case-insensitive prefix match through ``ILIKE``."""
        return sql(f"{column_sql} ILIKE ") + bind(f"{escape_like(text)}%") + sql(f" ESCAPE '{LIKE_ESCAPE}'")

    def soundex_match(self, column_sql: str, text: str) -> Statement:
        """Compare Soundex codes from fuzzystrmatch."""
        return sql(f"soundex({column_sql}) = soundex(") + bind(text) + sql(")")

    def difference_at_least(self, column_sql: str, text: str, threshold: int) -> Statement:
        """Use fuzzystrmatch's difference score, 0 to 4."""
        return sql(f"difference({column_sql}, ") + bind(text) + sql(") >= ") + bind(threshold)

    def levenshtein_within(self, column_sql: str, text: str, distance: int) -> Statement:
        """Use the bounded levenshtein_less_equal from fuzzystrmatch."""
        return sql(f"levenshtein_less_equal({column_sql}, ") + bind(text) + sql(", ") + bind(distance) + sql(") <= ") + bind(distance)

    def trigram_at_least(self, column_sql: str, text: str, threshold: float) -> Statement:
        """Use pg_trgm's similarity function, never the percent operator."""
        return sql(f"similarity({column_sql}, ") + bind(text) + sql(") >= ") + bind(threshold)

    def default_schema_statement(self) -> Statement | None:
        """Return the first schema on the search path."""
        return sql("SELECT current_schema()")

    def tables_statement(self, schemas: tuple[str, ...] | None) -> Statement:
        """List base tables with the planner's row estimate, which is negative before analysis."""
        return (
            sql(
                f"SELECT t.table_schema, t.table_name, {_ROW_ESTIMATE} FROM information_schema.tables t "
                "WHERE t.table_type = 'BASE TABLE' AND "
            )
            + _schema_predicate("t.table_schema", schemas)
            + sql(" ORDER BY t.table_schema, t.table_name")
        )

    def columns_statement(self, ref: TableRef) -> Statement:
        """Read columns, reporting the underlying type name for user-defined and array types."""
        return (
            sql(
                "SELECT c.column_name, CASE WHEN c.data_type IN ('USER-DEFINED', 'ARRAY') THEN c.udt_name "
                f"ELSE c.data_type END, c.is_nullable = 'YES', {_PRIMARY_KEY_POSITION} "
                "FROM information_schema.columns c WHERE c.table_schema = COALESCE("
            )
            + bind(ref.schema)
            + sql(", current_schema()) AND c.table_name = ")
            + bind(ref.name)
            + sql(" ORDER BY c.ordinal_position")
        )

    def foreign_keys_statement(self, ref: TableRef) -> Statement:
        """Read foreign keys, matching the referenced side on its position in the unique constraint."""
        return (
            sql(
                "SELECT rc.constraint_name, k.ordinal_position, k.column_name, r.table_schema, r.table_name, "
                "r.column_name FROM information_schema.referential_constraints rc "
                "JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name "
                "AND k.constraint_schema = rc.constraint_schema "
                "JOIN information_schema.key_column_usage r ON r.constraint_name = rc.unique_constraint_name "
                "AND r.constraint_schema = rc.unique_constraint_schema "
                "AND r.ordinal_position = k.position_in_unique_constraint WHERE k.table_schema = COALESCE("
            )
            + bind(ref.schema)
            + sql(", current_schema()) AND k.table_name = ")
            + bind(ref.name)
            + sql(" ORDER BY rc.constraint_name, k.ordinal_position")
        )

    def capability_probe_statement(self) -> Statement | None:
        """Report which fuzzy-matching extensions are installed."""
        return sql("SELECT extname FROM pg_catalog.pg_extension WHERE extname IN ('pg_trgm', 'fuzzystrmatch')")

    def probe_capabilities(self, names: Iterable[str]) -> frozenset[str]:
        """Map installed extension names to capabilities."""
        found: set[str] = set()
        for name in names:
            found |= _EXTENSION_CAPABILITIES.get(name, frozenset())
        return frozenset(found)
