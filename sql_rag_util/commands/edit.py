"""The metadata toolkit: tools that let an agent record what it learned.

Every edit is: check the agent's text, replace the entry, validate against the
catalog, refuse if the files on disk changed since they were loaded, write
canonically (refusing anything that would not read back identically), and
refresh, restoring the previous file if the refresh fails. Column edits carry
``source: agent, <date>``. The toolkit never adds or removes the ``sensitive``
and ``hidden`` flags; those belong to the developer.
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from sql_rag_util.atomic import atomic_write_text
from sql_rag_util.commands.spec import CommandResult, ToolSpec
from sql_rag_util.exceptions import ConfigurationError, MetadataConflictError, QuerySpecError
from sql_rag_util.metadata.model import ColumnMeta, ConceptMeta, GlossaryEntry, Metadata, RelationshipMeta, TableMeta
from sql_rag_util.query.spec import Filter
from sql_rag_util.schema.resolve import agent_name, resolve_column, resolve_table

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sql_rag_util.engine import SqlRag
    from sql_rag_util.metadata.store import MetadataStore

__all__ = ["EDIT_TABLE", "EDIT_COLUMN", "EDIT_RELATIONSHIP", "EDIT_CONCEPT", "EDIT_GLOSSARY", "TOOLKIT"]

_PROTECTED_FLAGS = frozenset({"sensitive", "hidden"})
_LINE_BREAKING = frozenset({"Cc", "Zl", "Zp"})
_BIDI_CONTROLS = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _source() -> str:
    return f"agent, {dt.date.today().isoformat()}"


def _line(value: str, what: str) -> str:
    text = value.strip()
    if any(unicodedata.category(ch) in _LINE_BREAKING or ch in _BIDI_CONTROLS for ch in text):
        raise QuerySpecError(f"{what} must be one line of plain text, without control or direction characters")
    return text


def _items(values: tuple[str, ...], what: str) -> tuple[str, ...]:
    items = tuple(_line(v, what) for v in values)
    if any("," in v for v in items):
        raise QuerySpecError(f"{what} entries cannot contain commas")
    return tuple(v for v in items if v)


def _prose(value: str) -> str:
    lines = [_line(line, "description") for line in value.strip().split("\n")]
    if any(line.startswith("#") for line in lines):
        raise QuerySpecError("description lines cannot start with '#'")
    return "\n".join(lines)


def _store(engine: SqlRag) -> MetadataStore:
    store = engine.store
    if store is None:
        raise ConfigurationError("metadata edits need a metadata_root")
    if not engine.config.allow_metadata_writes:
        raise ConfigurationError("metadata edits are disabled; set Config.allow_metadata_writes")
    return store


def _save(engine: SqlRag, candidate: Metadata, path: Path, write: Callable[[], Path]) -> None:
    store = _store(engine)
    if store.load() != engine.annotated.metadata:
        engine.refresh()
        raise MetadataConflictError("the metadata files changed on disk since they were loaded; they have been reloaded, so review them and retry")
    engine.validate_metadata(candidate)
    previous = path.read_text(encoding="utf-8") if path.is_file() else None
    write()
    try:
        engine.refresh()
    except BaseException:
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write_text(path, previous)
        raise


def _table_meta(engine: SqlRag, name: str) -> tuple[TableMeta, str]:
    table = resolve_table(engine.catalog, name)
    stem = agent_name(engine.catalog, table.ref)
    existing = engine.annotated.metadata.table(stem)
    return existing or TableMeta(stem, ""), stem


def _commit_table(engine: SqlRag, meta: TableMeta, what: str) -> CommandResult:
    store = _store(engine)
    if not meta.purpose:
        raise QuerySpecError(f"{meta.table} has no purpose yet; call edit_table with a purpose first")
    others = tuple(t for t in engine.annotated.metadata.tables if t.table != meta.table)
    candidate = replace(engine.annotated.metadata, tables=others + (meta,))
    path = store.table_path(meta.table)
    _save(engine, candidate, path, lambda: store.save_table(meta))
    return CommandResult({"written": store.root.joinpath(path).relative_to(store.root).as_posix(), "table": meta.table, "changed": what}, f"wrote {path.name}: {what}")


@dataclass(frozen=True, slots=True)
class EditTableArgs:
    """Arguments of ``edit_table``."""

    table: str = field(metadata={"description": "Table to describe."})
    purpose: str | None = field(default=None, metadata={"description": "One line saying what one row is. Required the first time a table is described."})
    description: str | None = field(default=None, metadata={"description": "Prose about the table that the schema does not say: units, lifecycle, gotchas."})
    synonyms: tuple[str, ...] | None = field(default=None, metadata={"description": "Other names people use for this table."})


def edit_table(engine: SqlRag, args: EditTableArgs) -> CommandResult:
    """Set a table's purpose, description, or synonyms."""
    meta, _ = _table_meta(engine, args.table)
    if args.purpose is not None:
        meta = replace(meta, purpose=_line(args.purpose, "purpose"))
    if args.description is not None:
        meta = replace(meta, description=_prose(args.description))
    if args.synonyms is not None:
        meta = replace(meta, synonyms=_items(args.synonyms, "synonyms"))
    return _commit_table(engine, meta, "table")


@dataclass(frozen=True, slots=True)
class EditColumnArgs:
    """Arguments of ``edit_column``."""

    table: str = field(metadata={"description": "Table the column belongs to."})
    column: str = field(metadata={"description": "Column to describe."})
    text: str = field(metadata={"description": "What the column means, beyond its name and type."})
    values: tuple[str, ...] | None = field(default=None, metadata={"description": "The meaningful values, for categorical columns."})
    synonyms: tuple[str, ...] | None = field(default=None, metadata={"description": "Other words people use for this column."})
    searchable: bool | None = field(default=None, metadata={"description": "Whether search_rows may match this text column."})


def edit_column(engine: SqlRag, args: EditColumnArgs) -> CommandResult:
    """Set a column's text, values, synonyms, or searchable flag."""
    meta, _ = _table_meta(engine, args.table)
    table = resolve_table(engine.catalog, args.table)
    column = resolve_column(table, args.column)
    existing = meta.column(column.name) or ColumnMeta(column.name, "")
    if existing.flags & _PROTECTED_FLAGS and args.searchable:
        raise QuerySpecError(f"column {column.name!r} is {', '.join(sorted(existing.flags & _PROTECTED_FLAGS))} and cannot be searchable")
    flags = set(existing.flags)
    if args.searchable is not None:
        flags.discard("searchable")
        if args.searchable:
            flags.add("searchable")
    updated = ColumnMeta(
        column.name,
        _line(args.text, "text"),
        frozenset(flags),
        _items(args.values, "values") if args.values is not None else existing.values,
        _items(args.synonyms, "synonyms") if args.synonyms is not None else existing.synonyms,
        _source(),
    )
    columns = tuple(c for c in meta.columns if c.name != column.name) + (updated,)
    return _commit_table(engine, replace(meta, columns=columns), f"column {column.name}")


@dataclass(frozen=True, slots=True)
class EditRelationshipArgs:
    """Arguments of ``edit_relationship``."""

    table: str = field(metadata={"description": "Table the relationship is navigated from."})
    name: str = field(metadata={"description": "Relationship name as shown by describe_table."})
    text: str = field(metadata={"description": "What following this relationship means."})


def edit_relationship(engine: SqlRag, args: EditRelationshipArgs) -> CommandResult:
    """Describe an existing relationship."""
    meta, _ = _table_meta(engine, args.table)
    name = _line(args.name, "name")
    entries = tuple(r for r in meta.relationships if r.name != name) + (RelationshipMeta(name, _line(args.text, "text")),)
    return _commit_table(engine, replace(meta, relationships=entries), f"relationship {name}")


@dataclass(frozen=True, slots=True)
class EditConceptArgs:
    """Arguments of ``edit_concept``."""

    table: str = field(metadata={"description": "Table the concept filters."})
    name: str = field(metadata={"description": "Lowercase identifier agents will use in query concepts."})
    text: str = field(metadata={"description": "What the concept means in business terms."})
    where: tuple[Filter, ...] = field(metadata={"description": "The filters that define it, exactly as query accepts them."})


def edit_concept(engine: SqlRag, args: EditConceptArgs) -> CommandResult:
    """Define or replace a named concept."""
    if not args.where:
        raise QuerySpecError("a concept needs at least one filter")
    meta, _ = _table_meta(engine, args.table)
    name = _line(args.name, "name")
    entries = tuple(c for c in meta.concepts if c.name != name) + (ConceptMeta(name, _line(args.text, "text"), tuple(args.where)),)
    return _commit_table(engine, replace(meta, concepts=entries), f"concept {name}")


@dataclass(frozen=True, slots=True)
class EditGlossaryArgs:
    """Arguments of ``edit_glossary``."""

    term: str = field(metadata={"description": "The domain term."})
    definition: str = field(metadata={"description": "What it means here."})
    synonyms: tuple[str, ...] | None = field(default=None, metadata={"description": "Other words for the term."})
    tables: tuple[str, ...] | None = field(default=None, metadata={"description": "Tables the term relates to."})


def edit_glossary(engine: SqlRag, args: EditGlossaryArgs) -> CommandResult:
    """Define or replace a glossary term."""
    store = _store(engine)
    term = _line(args.term, "term")
    if not term or any(ch in term for ch in ":[],"):
        raise QuerySpecError("term must be non-empty and contain no colon, bracket, or comma")
    entry = GlossaryEntry(term, _line(args.definition, "definition"), _items(args.synonyms or (), "synonyms"), _items(args.tables or (), "tables"))
    entries = tuple(e for e in engine.annotated.metadata.glossary if e.term.lower() != term.lower()) + (entry,)
    candidate: Metadata = replace(engine.annotated.metadata, glossary=entries)
    path = store.glossary_path()
    _save(engine, candidate, path, lambda: store.save_glossary(entries))
    return CommandResult({"written": path.name, "term": term}, f"wrote {path.name}: {term}")


EDIT_TABLE = ToolSpec("edit_table", "Edit table", "Record what a table is when its name does not say: purpose (one line), description, synonyms. Use it once you have confirmed the meaning from the data or the user.", EditTableArgs, edit_table, tier="full", mutating=True, examples=({"table": "orders", "purpose": "One row per customer order."},))
EDIT_COLUMN = ToolSpec("edit_column", "Edit column", "Record a column's meaning, its known values, synonyms, or mark a text column searchable. The edit is attributed to the agent with today's date for the developer to review.", EditColumnArgs, edit_column, tier="full", mutating=True, examples=({"table": "orders", "column": "status", "text": "Lifecycle state.", "values": ["open", "paid"]},))
EDIT_RELATIONSHIP = ToolSpec("edit_relationship", "Edit relationship", "Describe what following a relationship means, using its name from describe_table.", EditRelationshipArgs, edit_relationship, tier="full", mutating=True, examples=({"table": "orders", "name": "customer", "text": "The buyer."},))
EDIT_CONCEPT = ToolSpec("edit_concept", "Edit concept", "Define a business rule as a named filter set so future queries apply it by name. The filters are validated against the schema before saving.", EditConceptArgs, edit_concept, tier="full", mutating=True, examples=({"table": "orders", "name": "active", "text": "Orders still needing attention.", "where": [{"column": "status", "op": "in", "value": ["open", "paid"]}]},))
EDIT_GLOSSARY = ToolSpec("edit_glossary", "Edit glossary", "Define a domain term, its synonyms, and the tables it relates to, so get_context can match it.", EditGlossaryArgs, edit_glossary, tier="full", mutating=True, examples=({"term": "SKU", "definition": "Stock keeping unit.", "tables": ["products"]},))
TOOLKIT: tuple[ToolSpec, ...] = (EDIT_TABLE, EDIT_COLUMN, EDIT_RELATIONSHIP, EDIT_CONCEPT, EDIT_GLOSSARY)
