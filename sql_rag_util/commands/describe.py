"""The ``describe_table`` and ``list_tables`` tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from sql_rag_util.commands.spec import CommandResult, ToolSpec
from sql_rag_util.retrieval.cards import card_text, summary_text, table_card, table_summary
from sql_rag_util.schema.resolve import resolve_table

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag

__all__ = ["DescribeTableArgs", "ListTablesArgs", "describe_table", "list_tables", "DESCRIBE_TABLE", "LIST_TABLES"]


@dataclass(frozen=True, slots=True)
class DescribeTableArgs:
    """Arguments of ``describe_table``."""

    table: str = field(metadata={"description": "Table name as shown by list_tables or get_context."})
    format: Literal["json", "compact"] = field(default="json", metadata={"description": "json for the structured card; compact for the short text card."})


@dataclass(frozen=True, slots=True)
class ListTablesArgs:
    """Arguments of ``list_tables``."""

    format: Literal["json", "compact"] = field(default="json", metadata={"description": "json for objects; compact for one line per table."})


def describe_table(engine: SqlRag, args: DescribeTableArgs) -> CommandResult:
    """Return the full card of one table."""
    table = resolve_table(engine.catalog, args.table)
    card = table_card(engine.annotated, table, full=True)
    return CommandResult(card, card_text(card, full=True))


def list_tables(engine: SqlRag, args: ListTablesArgs) -> CommandResult:
    """Return every table's summary line."""
    summaries = [table_summary(engine.annotated, t) for t in engine.catalog.tables]
    return CommandResult({"tables": summaries}, "\n".join(summary_text(s) for s in summaries))


DESCRIBE_TABLE = ToolSpec(
    "describe_table",
    "Describe table",
    "Return the schema card of one table: columns with kind, key role, flags, known values, and meaning; "
    "relationships you can join through by name (use them as dotted paths in query, such as customer.name); "
    "concepts and measures you can apply by name in query. Call it for a table get_context did not already "
    "describe, or when you need column values before filtering.",
    DescribeTableArgs,
    describe_table,
    tier="standard",
    examples=({"table": "orders"}, {"table": "orders", "format": "compact"}),
)

LIST_TABLES = ToolSpec(
    "list_tables",
    "List tables",
    "List every table with its purpose, approximate row count, and column count. Use it to orient on a small "
    "schema; for a specific question prefer get_context, which returns only the relevant tables.",
    ListTablesArgs,
    list_tables,
    tier="standard",
    examples=({}, {"format": "compact"}),
)
