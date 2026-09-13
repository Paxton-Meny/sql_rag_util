"""Render metadata models to their canonical Markdown.

Parsing a canonical file and rendering it again yields identical bytes,
which the tests prove against the reference fixtures.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sql_rag_util.metadata.model import FORMAT_VERSION

if TYPE_CHECKING:
    from sql_rag_util.metadata.model import (
        ColumnMeta,
        DeclaredRelationship,
        GlossaryEntry,
        ProjectMeta,
        TableMeta,
    )
    from sql_rag_util.query.spec import Filter, Measure

__all__ = ["render_table", "render_project", "render_relationships", "render_glossary"]

_FLAG_ORDER = ("searchable", "sensitive", "hidden", "fulltext")


def _head(title: str, keys: list[tuple[str, str]]) -> list[str]:
    lines = [f"# {title}", "", f"format: {FORMAT_VERSION}"]
    lines.extend(f"{key}: {value}" for key, value in keys if value)
    return lines


def _list(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _filter_json(flt: Filter) -> dict[str, object]:
    out: dict[str, object] = {"column": flt.column, "op": str(flt.op)}
    if flt.value is not None:
        out["value"] = list(flt.value) if isinstance(flt.value, tuple) else flt.value
    return out


def _measure_json(measure: Measure) -> dict[str, object]:
    out: dict[str, object] = {"fn": str(measure.fn)}
    if measure.column is not None:
        out["column"] = measure.column
    return out


def _column(column: ColumnMeta) -> list[str]:
    flags = [f for f in _FLAG_ORDER if f in column.flags]
    suffix = f" [{', '.join(flags)}]" if flags else ""
    lines = [f"- {column.name}{suffix}: {column.text}"]
    if column.values:
        lines.append(f"  - values: {_list(column.values)}")
    if column.synonyms:
        lines.append(f"  - synonyms: {_list(column.synonyms)}")
    if column.source:
        lines.append(f"  - source: {column.source}")
    return lines


def _section(name: str, lines: list[str]) -> list[str]:
    return ["", f"## {name}", "", *lines] if lines else []


def render_table(meta: TableMeta) -> str:
    """Return the canonical ``tables/<stem>.md`` text."""
    lines = _head(meta.table, [("purpose", meta.purpose), ("synonyms", _list(meta.synonyms))])
    lines += _section("Description", meta.description.split("\n") if meta.description else [])
    lines += _section("Columns", [line for c in meta.columns for line in _column(c)])
    rel_lines = []
    for r in meta.relationships:
        rel_lines.append(f"- {r.name}: {r.text}")
        if r.renames:
            rel_lines.append(f"  - renames: {r.renames}")
    lines += _section("Relationships", rel_lines)
    concept_lines = []
    for c in meta.concepts:
        concept_lines += [f"- {c.name}: {c.text}", f"  - where: {json.dumps([_filter_json(f) for f in c.where])}"]
    lines += _section("Concepts", concept_lines)
    measure_lines = []
    for m in meta.measures:
        measure_lines += [f"- {m.name}: {m.text}", f"  - expr: {json.dumps(_measure_json(m.expr))}"]
    lines += _section("Measures", measure_lines)
    return "\n".join(lines) + "\n"


def render_project(meta: ProjectMeta) -> str:
    """Return the canonical ``project.md`` text; defaults are omitted."""
    keys = [
        ("description", meta.description),
        ("value_index", "on" if meta.value_index else ""),
        ("value_index_max_distinct", str(meta.value_index_max_distinct) if meta.value_index_max_distinct != 200 else ""),
        ("samples_per_column", str(meta.samples_per_column) if meta.samples_per_column != 3 else ""),
    ]
    return "\n".join(_head("project", keys)) + "\n"


def render_relationships(relationships: tuple[DeclaredRelationship, ...]) -> str:
    """Return the canonical ``relationships.md`` text."""
    lines = _head("relationships", [])
    for r in relationships:
        lines += [
            "",
            f"## {r.name}",
            "",
            f"from: {r.from_table} ({_list(r.from_columns)})",
            f"to: {r.to_table} ({_list(r.to_columns)})",
            f"cardinality: {r.cardinality}",
            f"text: {r.text}",
        ]
    return "\n".join(lines) + "\n"


def render_glossary(entries: tuple[GlossaryEntry, ...]) -> str:
    """Return the canonical ``glossary.md`` text."""
    term_lines = []
    for e in entries:
        term_lines.append(f"- {e.term}: {e.definition}")
        if e.synonyms:
            term_lines.append(f"  - synonyms: {_list(e.synonyms)}")
        if e.tables:
            term_lines.append(f"  - tables: {_list(e.tables)}")
    return "\n".join(_head("glossary", []) + _section("Terms", term_lines)) + "\n"
