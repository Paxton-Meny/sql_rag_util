"""Merge metadata into the catalog and validate every reference it makes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import (
    MetadataFormatError,
    SqlRagError,
    UnknownConceptError,
    UnknownMeasureError,
)
from sql_rag_util.metadata.writer import render_glossary, render_project, render_relationships, render_table
from sql_rag_util.query.aggregate import measure_sql
from sql_rag_util.query.joins import JoinPlan
from sql_rag_util.query.policy import ColumnPolicy
from sql_rag_util.schema.model import TEXT_KINDS, Relationship
from sql_rag_util.schema.resolve import resolve_column, resolve_table

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.metadata.model import ConceptMeta, MeasureMeta, Metadata, TableMeta
    from sql_rag_util.query.spec import Filter, Measure
    from sql_rag_util.schema.model import Catalog, TableInfo, TableRef

__all__ = ["AnnotatedCatalog", "annotate"]

_VERSION_LENGTH = 12


@dataclass(frozen=True, slots=True)
class AnnotatedCatalog:
    """The catalog with metadata applied.

    Parameters
    ----------
    catalog
        The agent's view: renamed and declared relationships applied, hidden
        columns removed, along with any primary key or foreign key they take part in.
    metadata
        The metadata as parsed.
    policy
        Hidden and sensitive columns.
    table_meta
        Table metadata by ref.
    searchable
        Searchable column names by ref, in metadata order.
    fulltext
        Columns flagged fulltext by ref.
    concepts
        Concepts by ref and name.
    measures
        Measures by ref and name.
    version
        Hash over the full catalog structure and metadata, exposed as ``schema_version``.
    """

    catalog: Catalog
    metadata: Metadata
    policy: ColumnPolicy
    table_meta: Mapping[TableRef, TableMeta] = field(default_factory=dict)
    searchable: Mapping[TableRef, tuple[str, ...]] = field(default_factory=dict)
    fulltext: Mapping[TableRef, frozenset[str]] = field(default_factory=dict)
    concepts: Mapping[TableRef, Mapping[str, ConceptMeta]] = field(default_factory=dict)
    measures: Mapping[TableRef, Mapping[str, MeasureMeta]] = field(default_factory=dict)
    version: str = ""

    def concept_filters(self, ref: TableRef, names: tuple[str, ...]) -> tuple[Filter, ...]:
        """Return the filters of the named concepts on ``ref``, AND-ed by the caller."""
        available = self.concepts.get(ref, {})
        out: list[Filter] = []
        for name in names:
            if name not in available:
                raise UnknownConceptError(f"unknown concept {name!r} on {ref.qualified}", suggestions=tuple(available))
            out.extend(available[name].where)
        return tuple(out)

    def measure(self, ref: TableRef, name: str) -> Measure:
        """Return the named measure's expression."""
        available = self.measures.get(ref, {})
        if name not in available:
            raise UnknownMeasureError(f"unknown measure {name!r} on {ref.qualified}", suggestions=tuple(available))
        return available[name].expr


def _fail(stem: str, message: str) -> MetadataFormatError:
    return MetadataFormatError(message, path=f"tables/{stem}.md")


def _table_for(catalog: Catalog, stem: str) -> TableInfo:
    try:
        return resolve_table(catalog, stem)
    except SqlRagError as exc:
        raise _fail(stem, f"{exc}") from None


def _apply_relationships(catalog: Catalog, metadata: Metadata) -> Catalog:
    relationships = list(catalog.relationships)
    for declared in metadata.relationships:
        try:
            source, target = resolve_table(catalog, declared.from_table), resolve_table(catalog, declared.to_table)
            pairs = tuple((resolve_column(source, a).name, resolve_column(target, b).name) for a, b in zip(declared.from_columns, declared.to_columns, strict=True))
        except SqlRagError as exc:
            raise MetadataFormatError(f"{declared.name}: {exc}", path="relationships.md") from None
        if any(r.source == source.ref and r.name == declared.name for r in relationships):
            raise MetadataFormatError(f"{declared.name} collides with a generated relationship on {source.ref.qualified}", path="relationships.md")
        relationships.append(Relationship(declared.name, source.ref, target.ref, pairs, declared.cardinality, "declared", declared.text))
    for meta in metadata.tables:
        ref = _table_for(catalog, meta.table).ref
        for entry in meta.relationships:
            existing = entry.renames or entry.name
            index = next((i for i, r in enumerate(relationships) if r.source == ref and r.name == existing), None)
            if index is None:
                raise _fail(meta.table, f"relationship {existing!r} does not exist on {ref.qualified}")
            if entry.renames and any(r.source == ref and r.name == entry.name for r in relationships):
                raise _fail(meta.table, f"relationship name {entry.name!r} is already taken on {ref.qualified}")
            relationships[index] = replace(relationships[index], name=entry.name, description=entry.text)
    return replace(catalog, relationships=tuple(relationships))


def _validate_rules(dialect: Dialect, catalog: Catalog, policy: ColumnPolicy, table: TableInfo, meta: TableMeta, max_depth: int) -> None:
    column_names = {c.name for c in table.columns}
    for concept in meta.concepts:
        if concept.name in column_names:
            raise _fail(meta.table, f"concept {concept.name!r} collides with a column")
        plan = JoinPlan(catalog, policy, table, max_depth)
        for flt in concept.where:
            try:
                plan.resolve(flt.column)
            except SqlRagError as exc:
                raise _fail(meta.table, f"concept {concept.name!r}: {exc}") from None
    for measure in meta.measures:
        if measure.name in column_names or any(c.name == measure.name for c in meta.concepts):
            raise _fail(meta.table, f"measure {measure.name!r} collides with a column or concept")
        try:
            measure_sql(dialect, JoinPlan(catalog, policy, table, max_depth), measure.expr)
        except SqlRagError as exc:
            raise _fail(meta.table, f"measure {measure.name!r}: {exc}") from None


def _without_hidden(table: TableInfo, hidden: frozenset[str]) -> TableInfo:
    columns = tuple(c for c in table.columns if c.name not in hidden)
    if hidden & set(table.primary_key):
        columns = tuple(replace(c, pk_position=None) for c in columns)
    return replace(table, columns=columns)


def _agent_catalog(catalog: Catalog, policy: ColumnPolicy) -> Catalog:
    tables = tuple(_without_hidden(t, policy.hidden.get(t.ref, frozenset())) for t in catalog.tables)
    foreign_keys = tuple(
        fk for fk in catalog.foreign_keys
        if not any(policy.is_hidden(fk.table, c) for c in fk.columns) and not any(policy.is_hidden(fk.referenced, c) for c in fk.referenced_columns)
    )
    return replace(catalog, tables=tables, foreign_keys=foreign_keys)


def _version(catalog: Catalog, metadata: Metadata) -> str:
    text = catalog.fingerprint + render_project(metadata.project) + render_relationships(metadata.relationships) + render_glossary(metadata.glossary)
    text += "".join(render_table(t) for t in metadata.tables)
    return hashlib.sha256(text.encode()).hexdigest()[:_VERSION_LENGTH]


def annotate(catalog: Catalog, metadata: Metadata, dialect: Dialect, *, max_join_depth: int = 2) -> AnnotatedCatalog:
    """Validate ``metadata`` against ``catalog`` and return the merged view.

    Raises
    ------
    MetadataFormatError
        Naming the file whenever metadata refers to something the catalog lacks
        or a rule the query layer would refuse.
    """
    hidden: dict[TableRef, frozenset[str]] = {}
    sensitive: dict[TableRef, frozenset[str]] = {}
    table_meta: dict[TableRef, TableMeta] = {}
    searchable: dict[TableRef, tuple[str, ...]] = {}
    fulltext: dict[TableRef, frozenset[str]] = {}
    for meta in metadata.tables:
        table = _table_for(catalog, meta.table)
        if table.ref in table_meta:
            raise _fail(meta.table, f"two files describe {table.ref.qualified}")
        table_meta[table.ref] = meta
        hidden_names, sensitive_names, searchable_names, fulltext_names = set(), set(), [], set()
        for column in meta.columns:
            try:
                info = resolve_column(table, column.name)
            except SqlRagError as exc:
                raise _fail(meta.table, str(exc)) from None
            if info.name != column.name:
                raise _fail(meta.table, f"column {column.name!r} must be written as {info.name!r}")
            if "hidden" in column.flags:
                hidden_names.add(info.name)
            if "sensitive" in column.flags:
                sensitive_names.add(info.name)
            if "searchable" in column.flags or "fulltext" in column.flags:
                if info.kind not in TEXT_KINDS:
                    raise _fail(meta.table, f"column {info.name!r} is {info.kind} and cannot be searchable")
                searchable_names.append(info.name)
            if "fulltext" in column.flags:
                fulltext_names.add(info.name)
        if len(hidden_names) == len(table.columns):
            raise _fail(meta.table, f"every column of {table.ref.qualified} is hidden; leave the table out of scope instead")
        hidden[table.ref], sensitive[table.ref] = frozenset(hidden_names), frozenset(sensitive_names)
        searchable[table.ref], fulltext[table.ref] = tuple(searchable_names), frozenset(fulltext_names)
    for entry in metadata.glossary:
        for name in entry.tables:
            try:
                resolve_table(catalog, name)
            except SqlRagError as exc:
                raise MetadataFormatError(f"{entry.term}: {exc}", path="glossary.md") from None
    policy = ColumnPolicy(hidden, sensitive)
    merged = _apply_relationships(catalog, metadata)
    agent = _agent_catalog(merged, policy)
    concepts = {ref: {c.name: c for c in meta.concepts} for ref, meta in table_meta.items()}
    measures = {ref: {m.name: m for m in meta.measures} for ref, meta in table_meta.items()}
    for ref, meta in table_meta.items():
        _validate_rules(dialect, agent, policy, agent.table(ref), meta, max_join_depth)  # type: ignore[arg-type]
    return AnnotatedCatalog(agent, metadata, policy, table_meta, searchable, fulltext, concepts, measures, _version(merged, metadata))
