"""Frozen value types describing an introspected database.

The snapshot is a :class:`Catalog`. The word "schema" is reserved for the
database namespace in :class:`TableRef` and for JSON Schema elsewhere.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "ColumnKind",
    "TableRef",
    "ColumnInfo",
    "TableInfo",
    "ForeignKeyInfo",
    "Relationship",
    "Catalog",
    "Cardinality",
    "CARDINALITIES",
    "NUMERIC_KINDS",
    "TEXT_KINDS",
]


class ColumnKind(enum.StrEnum):
    """Dialect-independent classification of a column's native type."""

    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    TEXT = "text"
    BOOLEAN = "boolean"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    BINARY = "binary"
    JSON = "json"
    UUID = "uuid"
    OTHER = "other"


NUMERIC_KINDS: frozenset[ColumnKind] = frozenset(
    {ColumnKind.INTEGER, ColumnKind.FLOAT, ColumnKind.DECIMAL}
)
TEXT_KINDS: frozenset[ColumnKind] = frozenset({ColumnKind.TEXT, ColumnKind.UUID})

Cardinality = Literal["to_one", "to_many"]
CARDINALITIES: tuple[Cardinality, ...] = ("to_one", "to_many")


@dataclass(frozen=True, slots=True)
class TableRef:
    """Identity of a table inside an optional namespace.

    Parameters
    ----------
    schema
        Namespace the table lives in, or ``None`` for the dialect default.
    name
        Table name as stored in the catalog.
    """

    schema: str | None
    name: str

    @property
    def qualified(self) -> str:
        """Return ``schema.name`` when a schema is set, else ``name``."""
        return f"{self.schema}.{self.name}" if self.schema else self.name


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    """One column of a table.

    Parameters
    ----------
    name
        Column name as stored in the catalog.
    native_type
        The type name the database reports.
    kind
        Dialect-independent classification of ``native_type``.
    nullable
        Whether the column admits NULL.
    pk_position
        One-based position in the primary key, or ``None``.
    """

    name: str
    native_type: str
    kind: ColumnKind
    nullable: bool
    pk_position: int | None = None


@dataclass(frozen=True, slots=True)
class TableInfo:
    """One table with its columns and primary key.

    Parameters
    ----------
    ref
        Identity of the table.
    columns
        Columns in ordinal order.
    row_estimate
        Approximate row count from the catalog, or ``None`` when unknown.
    """

    ref: TableRef
    columns: tuple[ColumnInfo, ...]
    row_estimate: int | None = None

    @property
    def primary_key(self) -> tuple[str, ...]:
        """Return primary key column names in key order."""
        keyed = [c for c in self.columns if c.pk_position is not None]
        return tuple(c.name for c in sorted(keyed, key=lambda c: c.pk_position or 0))

    def column(self, name: str) -> ColumnInfo | None:
        """Return the column named ``name`` exactly, or ``None``."""
        return next((c for c in self.columns if c.name == name), None)


@dataclass(frozen=True, slots=True)
class ForeignKeyInfo:
    """A foreign key constraint as the database declares it.

    Parameters
    ----------
    table
        The referencing table.
    columns
        Referencing columns in constraint order.
    referenced
        The referenced table.
    referenced_columns
        Referenced columns in the same order as ``columns``.
    name
        Constraint name when the database reports one.
    """

    table: TableRef
    columns: tuple[str, ...]
    referenced: TableRef
    referenced_columns: tuple[str, ...]
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Relationship:
    """A navigable link from one table to another.

    Parameters
    ----------
    name
        Agent-facing name, unique per source table.
    source
        The table the relationship is navigated from.
    target
        The table reached.
    pairs
        ``(source_column, target_column)`` pairs in constraint order.
    cardinality
        ``to_one`` when at most one target row matches, else ``to_many``.
    origin
        ``foreign_key`` when derived from a constraint, ``declared`` from metadata.
    description
        Text from metadata, or an empty string.
    """

    name: str
    source: TableRef
    target: TableRef
    pairs: tuple[tuple[str, str], ...]
    cardinality: Cardinality
    origin: Literal["foreign_key", "declared"]
    description: str = ""


@dataclass(frozen=True, slots=True)
class Catalog:
    """Immutable snapshot of the introspected database.

    Parameters
    ----------
    dialect
        Name of the dialect the snapshot was read with.
    tables
        Every table, in catalog order.
    foreign_keys
        Every foreign key constraint.
    relationships
        Derived and declared relationships.
    capabilities
        Dialect feature names available on this connection.
    fingerprint
        Stable hash of the snapshot contents.
    """

    dialect: str
    tables: tuple[TableInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    capabilities: frozenset[str] = field(default_factory=frozenset)
    fingerprint: str = ""

    def table(self, ref: TableRef) -> TableInfo | None:
        """Return the table with identity ``ref``, or ``None``."""
        return next((t for t in self.tables if t.ref == ref), None)

    def require(self, ref: TableRef) -> TableInfo:
        """Return the table with identity ``ref``.

        Raises
        ------
        LookupError
            When the catalog has no such table, which callers treat as a bug.
        """
        table = self.table(ref)
        if table is None:
            raise LookupError(f"{ref.qualified} is not in the catalog")
        return table

    def relationships_of(self, ref: TableRef) -> tuple[Relationship, ...]:
        """Return relationships navigated from ``ref``, in catalog order."""
        return tuple(r for r in self.relationships if r.source == ref)
