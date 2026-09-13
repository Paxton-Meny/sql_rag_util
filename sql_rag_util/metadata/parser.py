"""Per-file parsers for the metadata format. Every rejection names the file and line."""

from __future__ import annotations

import re

from sql_rag_util.exceptions import QuerySpecError
from sql_rag_util.metadata.document import Document, bullets, json_sub, list_value, only_subs, prose, split_document
from sql_rag_util.metadata.model import (
    COLUMN_FLAGS,
    ColumnMeta,
    ConceptMeta,
    DeclaredRelationship,
    GlossaryEntry,
    MeasureMeta,
    ProjectMeta,
    RelationshipMeta,
    TableMeta,
)
from sql_rag_util.query.spec import Filter, Measure

__all__ = ["parse_table", "parse_project", "parse_relationships", "parse_glossary"]

_KEY_LINE = re.compile(r"^([a-z_]+): (.*)$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOWER_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_TABLE_COLUMNS = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*) \(([^()]+)\)$")
_TABLE_SECTIONS = ("Description", "Columns", "Relationships", "Concepts", "Measures")
_PROJECT_KEYS = ("description", "value_index", "value_index_max_distinct", "samples_per_column")
_MAX_DISTINCT = 1000
_MAX_SAMPLES = 10


def _columns(doc: Document, lines: list[tuple[int, str]]) -> tuple[ColumnMeta, ...]:
    out = []
    for b in bullets(doc, lines):
        if not _IDENTIFIER.match(b.name):
            raise doc.fail(f"column name {b.name!r} is not an identifier", b.line)
        for flag in b.flags:
            if flag not in COLUMN_FLAGS:
                raise doc.fail(f"unknown flag {flag!r}; allowed: {', '.join(sorted(COLUMN_FLAGS))}", b.line)
        flags = frozenset(b.flags)
        if {"sensitive", "hidden"} <= flags or {"searchable", "hidden"} <= flags:
            raise doc.fail("hidden cannot combine with sensitive or searchable", b.line)
        only_subs(doc, b, ("values", "synonyms", "source"))
        source = b.subs.get("source", (None, 0))[0]
        out.append(ColumnMeta(b.name, b.text, flags, list_value(b.subs.get("values", ("", 0))[0]), list_value(b.subs.get("synonyms", ("", 0))[0]), source))
    return tuple(out)


def _relationships(doc: Document, lines: list[tuple[int, str]]) -> tuple[RelationshipMeta, ...]:
    out = []
    for b in bullets(doc, lines):
        if b.flags or not _IDENTIFIER.match(b.name):
            raise doc.fail(f"relationship {b.name!r} takes no flags and must be an identifier", b.line)
        only_subs(doc, b, ("renames",))
        out.append(RelationshipMeta(b.name, b.text, b.subs.get("renames", (None, 0))[0]))
    return tuple(out)


def _concepts(doc: Document, lines: list[tuple[int, str]]) -> tuple[ConceptMeta, ...]:
    out = []
    for b in bullets(doc, lines):
        if b.flags or not _LOWER_IDENTIFIER.match(b.name):
            raise doc.fail(f"concept {b.name!r} must be a lowercase identifier without flags", b.line)
        only_subs(doc, b, ("where",))
        raw = json_sub(doc, b, "where")
        line = b.subs["where"][1]
        if not isinstance(raw, list) or not raw or not all(isinstance(f, dict) for f in raw):
            raise doc.fail("where must be a non-empty JSON array of filter objects", line)
        try:
            where = tuple(Filter(**{str(k): v for k, v in f.items()}) for f in raw)
        except (QuerySpecError, TypeError) as exc:
            raise doc.fail(f"invalid filter: {exc}", line) from None
        out.append(ConceptMeta(b.name, b.text, where))
    return tuple(out)


def _measures(doc: Document, lines: list[tuple[int, str]]) -> tuple[MeasureMeta, ...]:
    out = []
    for b in bullets(doc, lines):
        if b.flags or not _LOWER_IDENTIFIER.match(b.name):
            raise doc.fail(f"measure {b.name!r} must be a lowercase identifier without flags", b.line)
        only_subs(doc, b, ("expr",))
        raw = json_sub(doc, b, "expr")
        line = b.subs["expr"][1]
        if not isinstance(raw, dict) or set(raw) - {"fn", "column"} or "fn" not in raw:
            raise doc.fail("expr must be a JSON object with fn and optionally column", line)
        try:
            expr = Measure(raw["fn"], raw.get("column"), b.name)
        except (QuerySpecError, TypeError) as exc:
            raise doc.fail(f"invalid measure: {exc}", line) from None
        out.append(MeasureMeta(b.name, b.text, expr))
    return tuple(out)


def _section(doc: Document, name: str) -> list[tuple[int, str]]:
    return doc.sections.get(name, (0, []))[1]


def _check_keys(doc: Document, allowed: tuple[str, ...], required: tuple[str, ...]) -> None:
    for key, (_, line) in doc.header.items():
        if key not in allowed:
            raise doc.fail(f"unknown header key {key!r}; allowed: {', '.join(allowed)}", line)
    for key in required:
        if key not in doc.header:
            raise doc.fail(f"missing required header key {key!r}", 3)
    for name, (line, _) in doc.sections.items():
        if name not in (_TABLE_SECTIONS if allowed[0] == "purpose" else ()):
            raise doc.fail(f"unknown section {name!r}", line)


def parse_table(text: str, path: str, stem: str) -> TableMeta:
    """Parse a ``tables/<stem>.md`` file."""
    doc = split_document(text, path)
    _check_keys(doc, ("purpose", "synonyms"), ("purpose",))
    if doc.title != stem:
        raise doc.fail(f"heading {doc.title!r} must equal the file stem {stem!r}", 1)
    return TableMeta(
        stem,
        doc.header["purpose"][0],
        list_value(doc.header.get("synonyms", ("", 0))[0]),
        prose(_section(doc, "Description")),
        _columns(doc, _section(doc, "Columns")),
        _relationships(doc, _section(doc, "Relationships")),
        _concepts(doc, _section(doc, "Concepts")),
        _measures(doc, _section(doc, "Measures")),
    )


def parse_project(text: str, path: str) -> ProjectMeta:
    """Parse ``project.md``."""
    doc = split_document(text, path)
    if doc.title != "project":
        raise doc.fail("heading must be 'project'", 1)
    _check_keys(doc, _PROJECT_KEYS, ())
    if doc.sections:
        raise doc.fail("project.md has no sections", next(iter(doc.sections.values()))[0])
    toggle, line = doc.header.get("value_index", ("off", 3))
    if toggle not in ("on", "off"):
        raise doc.fail("value_index must be 'on' or 'off'", line)
    numbers = {}
    for key, cap, default in (("value_index_max_distinct", _MAX_DISTINCT, 200), ("samples_per_column", _MAX_SAMPLES, 3)):
        raw, line = doc.header.get(key, (str(default), 3))
        if not raw.isdigit() or not 1 <= int(raw) <= cap:
            raise doc.fail(f"{key} must be an integer from 1 to {cap}", line)
        numbers[key] = int(raw)
    return ProjectMeta(doc.header.get("description", ("", 0))[0], toggle == "on", numbers["value_index_max_distinct"], numbers["samples_per_column"])


def _table_columns(doc: Document, value: str, line: int) -> tuple[str, tuple[str, ...]]:
    match = _TABLE_COLUMNS.match(value)
    if not match:
        raise doc.fail("expected '<table> (<column>, ...)'", line)
    return match.group(1), list_value(match.group(2))


def parse_relationships(text: str, path: str) -> tuple[DeclaredRelationship, ...]:
    """Parse ``relationships.md``."""
    doc = split_document(text, path)
    if doc.title != "relationships" or doc.header:
        raise doc.fail("heading must be 'relationships' with no header keys", 1)
    out = []
    for name, (line, lines) in doc.sections.items():
        if not _IDENTIFIER.match(name):
            raise doc.fail(f"relationship name {name!r} is not an identifier", line)
        keys: dict[str, tuple[str, int]] = {}
        for number, content in lines:
            if not content:
                continue
            match = _KEY_LINE.match(content)
            if not match or match.group(1) not in ("from", "to", "cardinality", "text") or match.group(1) in keys:
                raise doc.fail("expected one each of from, to, cardinality, text", number)
            keys[match.group(1)] = (match.group(2), number)
        missing = [k for k in ("from", "to", "cardinality", "text") if k not in keys]
        if missing:
            raise doc.fail(f"missing {', '.join(missing)}", line)
        from_table, from_columns = _table_columns(doc, *keys["from"])
        to_table, to_columns = _table_columns(doc, *keys["to"])
        if len(from_columns) != len(to_columns):
            raise doc.fail("from and to must list the same number of columns", keys["to"][1])
        if keys["cardinality"][0] not in ("to_one", "to_many"):
            raise doc.fail("cardinality must be to_one or to_many", keys["cardinality"][1])
        out.append(DeclaredRelationship(name, from_table, from_columns, to_table, to_columns, keys["cardinality"][0], keys["text"][0]))  # type: ignore[arg-type]
    return tuple(out)


def parse_glossary(text: str, path: str) -> tuple[GlossaryEntry, ...]:
    """Parse ``glossary.md``."""
    doc = split_document(text, path)
    if doc.title != "glossary" or doc.header or set(doc.sections) - {"Terms"}:
        raise doc.fail("heading must be 'glossary', no header keys, and only a 'Terms' section", 1)
    out, seen = [], set()
    for b in bullets(doc, doc.sections.get("Terms", (0, []))[1]):
        if b.flags:
            raise doc.fail("glossary terms take no flags", b.line)
        if b.name.lower() in seen:
            raise doc.fail(f"duplicate term {b.name!r}", b.line)
        seen.add(b.name.lower())
        only_subs(doc, b, ("synonyms", "tables"))
        out.append(GlossaryEntry(b.name, b.text, list_value(b.subs.get("synonyms", ("", 0))[0]), list_value(b.subs.get("tables", ("", 0))[0])))
    return tuple(out)
