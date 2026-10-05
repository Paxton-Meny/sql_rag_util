"""Frozen value types for project metadata. See ``docs/metadata-format.md``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sql_rag_util.query.spec import Filter, Measure
    from sql_rag_util.schema.model import Cardinality

__all__ = [
    "COLUMN_FLAGS",
    "FORMAT_VERSION",
    "ColumnMeta",
    "RelationshipMeta",
    "ConceptMeta",
    "MeasureMeta",
    "TableMeta",
    "DeclaredRelationship",
    "GlossaryEntry",
    "ProjectMeta",
    "Metadata",
]

FORMAT_VERSION = 1
COLUMN_FLAGS: frozenset[str] = frozenset({"searchable", "sensitive", "hidden", "fulltext"})


@dataclass(frozen=True, slots=True)
class ColumnMeta:
    """Developer context for one column."""

    name: str
    text: str
    flags: frozenset[str] = frozenset()
    values: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    source: str | None = None


@dataclass(frozen=True, slots=True)
class RelationshipMeta:
    """Text for a relationship, and optionally a rename of a generated one."""

    name: str
    text: str
    renames: str | None = None


@dataclass(frozen=True, slots=True)
class ConceptMeta:
    """A named filter set agents apply by name."""

    name: str
    text: str
    where: tuple[Filter, ...]


@dataclass(frozen=True, slots=True)
class MeasureMeta:
    """A named aggregate agents apply by name."""

    name: str
    text: str
    expr: Measure


@dataclass(frozen=True, slots=True)
class TableMeta:
    """Everything a table file carries.

    Parameters
    ----------
    table
        The file stem: a bare table name or ``schema.table``.
    """

    table: str
    purpose: str
    synonyms: tuple[str, ...] = ()
    description: str = ""
    columns: tuple[ColumnMeta, ...] = ()
    relationships: tuple[RelationshipMeta, ...] = ()
    concepts: tuple[ConceptMeta, ...] = ()
    measures: tuple[MeasureMeta, ...] = ()

    def column(self, name: str) -> ColumnMeta | None:
        """Return the entry for ``name``, or ``None``."""
        return next((c for c in self.columns if c.name == name), None)


@dataclass(frozen=True, slots=True)
class DeclaredRelationship:
    """A relationship the database does not declare as a foreign key."""

    name: str
    from_table: str
    from_columns: tuple[str, ...]
    to_table: str
    to_columns: tuple[str, ...]
    cardinality: Cardinality
    text: str


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    """A domain term."""

    term: str
    definition: str
    synonyms: tuple[str, ...] = ()
    tables: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectMeta:
    """Project-wide settings from ``project.md``."""

    description: str = ""
    value_index: bool = False
    value_index_max_distinct: int = 200
    samples_per_column: int = 3


@dataclass(frozen=True, slots=True)
class Metadata:
    """The whole metadata directory, parsed."""

    project: ProjectMeta = ProjectMeta()
    tables: tuple[TableMeta, ...] = ()
    relationships: tuple[DeclaredRelationship, ...] = ()
    glossary: tuple[GlossaryEntry, ...] = field(default=())

    def table(self, stem: str) -> TableMeta | None:
        """Return the table entry whose stem is ``stem``, or ``None``."""
        return next((t for t in self.tables if t.table == stem), None)
