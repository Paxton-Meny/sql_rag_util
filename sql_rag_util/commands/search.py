"""The ``search_rows`` tool: fuzzy retrieval over searchable columns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from sql_rag_util.commands.results import shape_rows, table_text
from sql_rag_util.commands.spec import CommandResult, ToolSpec
from sql_rag_util.exceptions import QuerySpecError
from sql_rag_util.query.compile import compile_query
from sql_rag_util.query.spec import QuerySpec
from sql_rag_util.schema.resolve import agent_name, closest, resolve_table
from sql_rag_util.search.strategies import SearchColumn, Strategy, default_strategies, search_where
from sql_rag_util.search.term import tokenize_term
from sql_rag_util.sql.render import render

if TYPE_CHECKING:
    from sql_rag_util.engine import SqlRag
    from sql_rag_util.query.joins import JoinPlan
    from sql_rag_util.sql.statement import Statement

__all__ = ["SearchRowsArgs", "search_rows", "SEARCH_ROWS"]


@dataclass(frozen=True, slots=True)
class SearchRowsArgs:
    """Arguments of ``search_rows``."""

    table: str = field(metadata={"description": "Table to search."})
    term: str = field(metadata={"description": "Words to find, such as a possibly misspelled name. Each word is matched against every searchable column."})
    columns: tuple[str, ...] | None = field(default=None, metadata={"description": "Subset of the table's searchable columns; omit for all of them."})
    match: Literal["all", "any"] = field(default="all", metadata={"description": "all: every word must match some column; any: one word is enough."})
    strategies: tuple[Strategy, ...] | None = field(default=None, metadata={"description": "Matching strategies; omit for contains plus the fuzzy strategies this database supports."})
    limit: int | None = field(default=None, metadata={"description": "Maximum rows; default 50, hard cap 500."})
    format: Literal["json", "compact"] = field(default="json", metadata={"description": "json for columns plus rows; compact for a tab-separated table."})


def _search_columns(engine: SqlRag, table, args: SearchRowsArgs) -> tuple[str, ...]:  # type: ignore[no-untyped-def]
    searchable = engine.annotated.searchable.get(table.ref, ())
    if not searchable:
        raise QuerySpecError(f"{agent_name(engine.catalog, table.ref)} has no searchable columns; mark columns searchable in its metadata")
    if not args.columns:
        return searchable
    chosen = []
    for name in args.columns:
        if name not in searchable:
            raise QuerySpecError(f"column {name!r} is not searchable on {agent_name(engine.catalog, table.ref)}", suggestions=closest(name, searchable) or searchable)
        chosen.append(name)
    return tuple(chosen)


def search_rows(engine: SqlRag, args: SearchRowsArgs) -> CommandResult:
    """Find rows whose searchable columns match the term."""
    table = resolve_table(engine.catalog, args.table)
    names = _search_columns(engine, table, args)
    tokens = tokenize_term(args.term, max_tokens=engine.limits.max_search_tokens)
    capabilities = engine.catalog.capabilities
    strategies = args.strategies or default_strategies(capabilities)
    fulltext = engine.annotated.fulltext.get(table.ref, frozenset())

    def predicate(plan: JoinPlan) -> Statement:
        columns = tuple(SearchColumn(n, plan.column_sql(engine.dialect, plan.resolve(n)), fulltext=n in fulltext) for n in names)
        return search_where(engine.dialect, capabilities, columns, tokens, strategies, match_all=args.match == "all")

    spec = QuerySpec(args.table, limit=args.limit)
    compiled = compile_query(engine.dialect, engine.catalog, engine.annotated.policy, spec, engine.limits, extra_filters=engine.scope_filters(table), extra_predicate=predicate)
    fetched = engine.executor.fetch(compiled.statement, command="search_rows", limit=compiled.limit)
    rows, cut = shape_rows(fetched.rows, engine.limits)
    notes = list(compiled.notes)
    if cut:
        notes.append(f"{cut} cells shortened to {engine.limits.max_cell_chars} characters.")
    if not rows:
        notes.append("0 rows. Try fewer words, match any, or a different spelling.")
    data = {"table": agent_name(engine.catalog, table.ref), "columns": list(compiled.columns), "rows": rows, "row_count": len(rows), "searched": list(names), "strategies": [str(s) for s in strategies]}
    if engine.config.reveal_sql:
        data["sql"] = render(compiled.statement, engine.executor.paramstyle)[0]
    return CommandResult(data, table_text(compiled.columns, rows), fetched.truncated, tuple(notes))


SEARCH_ROWS = ToolSpec(
    "search_rows",
    "Search rows",
    "Find rows by fuzzy text match over a table's searchable columns. Use it when you have a name or label that "
    "may be misspelled, partial, or split across columns (a full name against first_name and last_name). Each word "
    "of term is matched against every searchable column with contains plus the fuzzy strategies this database "
    "supports; with match all every word must hit. Returns the matching rows so you can take an exact id or value "
    "into query.",
    SearchRowsArgs,
    search_rows,
    tier="standard",
    examples=({"table": "customers", "term": "Jon Smyth"}, {"table": "customers", "term": "acme", "columns": ["name"], "match": "any", "limit": 5}),
)
