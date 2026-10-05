"""The ``query`` tool: one declarative read compiled to one statement."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from sql_rag_util.commands.diagnose import empty_result_notes
from sql_rag_util.commands.results import shape_rows, table_text
from sql_rag_util.commands.spec import CommandResult, ToolSpec
from sql_rag_util.query.compile import compile_query
from sql_rag_util.query.spec import AggregateFn, Measure, QuerySpec
from sql_rag_util.schema.resolve import agent_name, resolve_table
from sql_rag_util.sql.render import render

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag
    from sql_rag_util.schema.model import TableRef

__all__ = ["query", "QUERY"]

_EMPTY_NOTE = "0 rows. Check filter values against describe_table's known values, or find the row with search_rows."


def _expand_measures(engine: SqlRag, ref: TableRef, measures: tuple[Measure, ...]) -> tuple[Measure, ...]:
    out = []
    for measure in measures:
        if measure.fn is AggregateFn.MEASURE:
            named = engine.annotated.measure(ref, measure.column or "")
            out.append(replace(named, alias=measure.alias or named.alias))
        else:
            out.append(measure)
    return tuple(out)


def query(engine: SqlRag, spec: QuerySpec) -> CommandResult:
    """Compile, execute, and shape one query."""
    table = resolve_table(engine.catalog, spec.table)
    extra = engine.annotated.concept_filters(table.ref, spec.concepts) + engine.scope_filters(table)
    expanded = replace(spec, concepts=(), measures=_expand_measures(engine, table.ref, spec.measures))
    compiled = compile_query(engine.dialect, engine.catalog, engine.annotated.policy, expanded, engine.limits, extra_filters=extra)
    fetched = engine.executor.fetch(compiled.statement, command="query", limit=compiled.limit)
    rows, cut = shape_rows(fetched.rows, engine.limits)
    notes = list(compiled.notes)
    if cut:
        notes.append(f"{cut} cell{'s' if cut > 1 else ''} shortened to {engine.limits.max_cell_chars} characters.")
    if not rows:
        notes.extend(empty_result_notes(engine, table, spec.filters) or (_EMPTY_NOTE,))
    data = {"table": agent_name(engine.catalog, table.ref), "columns": list(compiled.columns), "rows": rows, "row_count": len(rows)}
    if engine.config.reveal_sql:
        data["sql"] = render(compiled.statement, engine.executor.paramstyle)[0]
    return CommandResult(data, table_text(compiled.columns, rows), fetched.truncated, tuple(notes))


QUERY = ToolSpec(
    "query",
    "Query",
    "Read rows or aggregates from one table, with joins along its relationships, as one bounded statement. "
    "Idioms: rows: columns plus filters. count: measures [{fn: count}] with no group_by. distinct values: "
    "group_by [column] with measures [{fn: count}]. join: dotted paths from describe_table relationships, "
    "for example columns [\"id\", \"customer.name\"] or a filter on \"customer.region\". aggregate: group_by plus "
    "measures such as {fn: sum, column: amount, alias: revenue}, then order by the alias. Apply a table's "
    "concepts by name and its named measures with {fn: measure, column: <name>}. Results are columns plus rows; "
    "read notes and truncated, and narrow with filters rather than raising limit. Never guess a text value: "
    "use the known values from describe_table or find it with search_rows.",
    QuerySpec,
    query,
    tier="minimal",
    examples=(
        {"table": "orders", "columns": ["id", "status", "customer.name"], "filters": [{"column": "status", "op": "in", "value": ["open", "paid"]}], "limit": 20},
        {"table": "orders", "measures": [{"fn": "count"}], "concepts": ["active"]},
        {"table": "orders", "group_by": ["status"], "measures": [{"fn": "count"}]},
        {"table": "orders", "group_by": ["customer.region"], "measures": [{"fn": "sum", "column": "amount", "alias": "revenue"}], "order": [{"by": "revenue", "direction": "desc"}]},
    ),
)
