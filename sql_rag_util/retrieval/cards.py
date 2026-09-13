"""Schema cards: the compact description of one table agents read.

A card exists as structured data and as one short text block. The text
follows the M-Schema idea: one line per column with kind, key role, flags,
and known values, then relationships, concepts, and measures by name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sql_rag_util.schema.resolve import agent_name

if TYPE_CHECKING:
    from sql_rag_util.metadata.annotate import AnnotatedCatalog
    from sql_rag_util.schema.model import TableInfo

__all__ = ["table_card", "card_text", "table_summary", "summary_text"]

_MAX_VALUES_IN_TEXT = 8


def _rows_text(rows: int | None) -> str:
    if rows is None:
        return ""
    if rows >= 1000:
        return f"~{rows / 1000:.0f}k rows"
    return f"~{rows} rows"


def _foreign_key_target(annotated: AnnotatedCatalog, table: TableInfo, column: str) -> str | None:
    for fk in annotated.catalog.foreign_keys:
        if fk.table == table.ref and fk.columns == (column,):
            return f"{agent_name(annotated.catalog, fk.referenced)}.{fk.referenced_columns[0]}"
    return None


def table_card(annotated: AnnotatedCatalog, table: TableInfo, *, full: bool = True) -> dict[str, Any]:
    """Return the structured card for ``table``.

    Parameters
    ----------
    full
        Include the description prose and column text; ``False`` gives the
        shorter form used inside context packs.
    """
    meta = annotated.table_meta.get(table.ref)
    policy = annotated.policy
    columns = []
    for column in policy.visible(table.ref, table.columns):
        column_meta = meta.column(column.name) if meta else None
        flags = sorted(f for f in ("searchable", "sensitive", "fulltext") if column_meta and f in column_meta.flags)
        entry: dict[str, Any] = {"name": column.name, "kind": str(column.kind), "type": column.native_type, "nullable": column.nullable}
        if column.pk_position is not None:
            entry["key"] = "pk"
        if (target := _foreign_key_target(annotated, table, column.name)) is not None:
            entry["fk"] = target
        if flags:
            entry["flags"] = flags
        if column_meta:
            if full and column_meta.text:
                entry["text"] = column_meta.text
            if column_meta.values:
                entry["values"] = list(column_meta.values)
            if full and column_meta.synonyms:
                entry["synonyms"] = list(column_meta.synonyms)
        columns.append(entry)
    relationships = [
        {"name": r.name, "to": agent_name(annotated.catalog, r.target), "cardinality": r.cardinality, "text": r.description}
        for r in annotated.catalog.relationships_of(table.ref)
    ]
    card: dict[str, Any] = {
        "table": agent_name(annotated.catalog, table.ref),
        "purpose": meta.purpose if meta else "",
        "rows": table.row_estimate,
        "columns": columns,
        "relationships": relationships,
        "concepts": [{"name": c.name, "text": c.text} for c in (meta.concepts if meta else ())],
        "measures": [{"name": m.name, "text": m.text} for m in (meta.measures if meta else ())],
    }
    if full:
        card["description"] = meta.description if meta else ""
        card["synonyms"] = list(meta.synonyms) if meta else []
    return card


def _column_text(entry: dict[str, Any], *, full: bool) -> str:
    parts = [f"{entry['name']} {entry['kind'].upper()}"]
    if entry.get("key"):
        parts.append("pk")
    if entry.get("fk"):
        parts.append(f"fk->{entry['fk']}")
    if entry.get("flags"):
        parts.append(f"[{', '.join(entry['flags'])}]")
    if entry.get("values"):
        shown = entry["values"][:_MAX_VALUES_IN_TEXT]
        more = f",+{len(entry['values']) - len(shown)}" if len(entry["values"]) > len(shown) else ""
        parts.append("{" + ",".join(shown) + more + "}")
    text = " ".join(parts)
    if full and entry.get("text"):
        text += f": {entry['text']}"
    return text


def card_text(card: dict[str, Any], *, full: bool = True) -> str:
    """Return the compact text of a card."""
    head = f"# {card['table']}"
    if rows := _rows_text(card.get("rows")):
        head += f" ({rows})"
    if card.get("purpose"):
        head += f": {card['purpose']}"
    lines = [head]
    if full and card.get("description"):
        lines.append(card["description"].replace("\n", " "))
    lines.append(" | ".join(_column_text(c, full=full) for c in card["columns"]))
    if card["relationships"]:
        rels = []
        for r in card["relationships"]:
            item = f"{r['name']} -> {r['to']} ({r['cardinality']})"
            if full and r["text"]:
                item += f": {r['text']}"
            rels.append(item)
        lines.append("rel: " + " | ".join(rels))
    for key in ("concepts", "measures"):
        if card[key]:
            items = [f"{i['name']}: {i['text']}" if full and i["text"] else i["name"] for i in card[key]]
            lines.append(f"{key}: " + " | ".join(items))
    return "\n".join(lines)


def table_summary(annotated: AnnotatedCatalog, table: TableInfo) -> dict[str, Any]:
    """Return the one-line form of a table for listings."""
    meta = annotated.table_meta.get(table.ref)
    return {
        "table": agent_name(annotated.catalog, table.ref),
        "purpose": meta.purpose if meta else "",
        "rows": table.row_estimate,
        "columns": len(annotated.policy.visible(table.ref, table.columns)),
    }


def summary_text(summary: dict[str, Any]) -> str:
    """Return one line for a table summary."""
    facts = [f"{summary['columns']} cols"]
    if rows := _rows_text(summary.get("rows")):
        facts.insert(0, rows)
    line = f"{summary['table']} ({', '.join(facts)})"
    return f"{line}: {summary['purpose']}" if summary["purpose"] else line
