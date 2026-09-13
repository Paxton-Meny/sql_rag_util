"""Compile a :class:`~sql_rag_util.query.spec.QuerySpec` into one statement."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import LimitExceededError, QuerySpecError
from sql_rag_util.query.aggregate import measure_sql
from sql_rag_util.query.filters import build_predicate
from sql_rag_util.query.joins import JoinPlan
from sql_rag_util.query.spec import Filter
from sql_rag_util.schema.model import ColumnKind
from sql_rag_util.schema.resolve import resolve_table
from sql_rag_util.sql.statement import Statement, join, sql

if TYPE_CHECKING:
    from sql_rag_util.config import Limits
    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.query.policy import ColumnPolicy
    from sql_rag_util.query.spec import QuerySpec
    from sql_rag_util.schema.model import Catalog, TableInfo

__all__ = ["Compiled", "compile_query"]

_FAN_OUT_NOTE = "Rows may repeat: a to_many relationship was joined without grouping."


@dataclass(frozen=True, slots=True)
class Compiled:
    """A compiled spec.

    Parameters
    ----------
    statement
        The single statement to execute.
    columns
        Result column names in select order.
    table
        The base table.
    limit
        The row cap requested. The statement binds one more so truncation
        can be detected.
    notes
        Advice for the agent, such as fan-out or omitted columns.
    """

    statement: Statement
    columns: tuple[str, ...]
    table: TableInfo
    limit: int
    notes: tuple[str, ...]


def _limit(spec: QuerySpec, limits: Limits) -> int:
    if spec.limit is None:
        return limits.max_rows
    if spec.limit > limits.hard_max_rows:
        raise LimitExceededError(f"limit {spec.limit} exceeds the maximum of {limits.hard_max_rows}")
    return spec.limit


def _select_rows(dialect: Dialect, plan: JoinPlan, spec: QuerySpec, limits: Limits, notes: list[str]) -> tuple[list[Statement], list[str]]:
    if spec.columns:
        paths = list(dict.fromkeys(spec.columns))
        if len(paths) > limits.max_columns:
            raise LimitExceededError(f"at most {limits.max_columns} columns per query")
    else:
        selectable = plan.policy.selectable(plan.base.ref, plan.base.columns)
        paths = [c.name for c in selectable if c.kind is not ColumnKind.BINARY]
        if len(paths) > limits.max_columns:
            notes.append(f"{len(paths) - limits.max_columns} columns omitted; name the columns you need.")
            paths = paths[: limits.max_columns]
    items, names = [], []
    for path in paths:
        resolved = plan.resolve(path)
        items.append(sql(f"{plan.column_sql(dialect, resolved)} AS {dialect.quote(path)}"))
        names.append(path)
    return items, names


def _select_aggregate(dialect: Dialect, plan: JoinPlan, spec: QuerySpec, limits: Limits) -> tuple[list[Statement], list[str], list[str]]:
    if len(spec.group_by) > limits.max_group_by:
        raise LimitExceededError(f"at most {limits.max_group_by} group_by columns")
    if len(spec.measures) > limits.max_measures:
        raise LimitExceededError(f"at most {limits.max_measures} measures")
    items, names, group_sql = [], [], []
    for path in dict.fromkeys(spec.group_by):
        resolved = plan.resolve(path)
        column_sql = plan.column_sql(dialect, resolved)
        items.append(sql(f"{column_sql} AS {dialect.quote(path)}"))
        names.append(path)
        group_sql.append(column_sql)
    for measure in spec.measures:
        items.append(measure_sql(dialect, plan, measure))
        names.append(measure.name)
    return items, names, group_sql


def _where(dialect: Dialect, plan: JoinPlan, filters: tuple[Filter, ...], limits: Limits, now: dt.datetime | None) -> Statement | None:
    if not filters:
        return None
    predicates = []
    for flt in filters:
        resolved = plan.resolve(flt.column)
        predicates.append(build_predicate(dialect, plan.column_sql(dialect, resolved), resolved.column, flt, max_in_values=limits.max_in_values, now=now))
    return sql("WHERE ") + join(" AND ", (sql("(") + p + sql(")") for p in predicates))


def _order(dialect: Dialect, plan: JoinPlan, spec: QuerySpec, group_sql: list[str]) -> str | None:
    terms = []
    for term in spec.order:
        if term.by in spec.names:
            target = dialect.quote(term.by)
        else:
            target = plan.column_sql(dialect, plan.resolve(term.by))
        terms.append(f"{target} {term.direction.upper()}")
    if terms:
        return "ORDER BY " + ", ".join(terms)
    if spec.measures and spec.group_by:
        return f"ORDER BY {dialect.quote(spec.names[0])} DESC"
    if spec.group_by:
        return "ORDER BY " + ", ".join(group_sql)
    if spec.measures:
        return None
    key = plan.base.primary_key or (plan.base.columns[0].name,)
    return "ORDER BY " + ", ".join(f"{dialect.quote(plan.base_alias)}.{dialect.quote(c)}" for c in key)


def compile_query(
    dialect: Dialect,
    catalog: Catalog,
    policy: ColumnPolicy,
    spec: QuerySpec,
    limits: Limits,
    *,
    extra_filters: tuple[Filter, ...] = (),
    now: dt.datetime | None = None,
) -> Compiled:
    """Return the single statement for ``spec``.

    Parameters
    ----------
    extra_filters
        Developer scope and concept predicates, AND-ed with the spec's own.
    now
        Reference time for ``since_days``; defaults to the current UTC time.
    """
    if len(spec.filters) > limits.max_filters:
        raise LimitExceededError(f"at most {limits.max_filters} filters per query")
    if spec.concepts:
        raise QuerySpecError("concepts must be expanded before compilation")
    table = resolve_table(catalog, spec.table)
    plan = JoinPlan(catalog, policy, table, limits.max_join_depth)
    notes: list[str] = []
    group_sql: list[str] = []
    if spec.is_aggregate:
        items, names, group_sql = _select_aggregate(dialect, plan, spec, limits)
    else:
        items, names = _select_rows(dialect, plan, spec, limits, notes)
    where = _where(dialect, plan, spec.filters + extra_filters, limits, now)
    order = _order(dialect, plan, spec, group_sql)
    body = plan.from_clause(dialect)
    if where is not None:
        body = body + sql(" ") + where
    if group_sql:
        body = body + sql(" GROUP BY " + ", ".join(group_sql))
    if order:
        body = body + sql(" " + order)
    if plan.fans_out and not spec.is_aggregate:
        notes.append(_FAN_OUT_NOTE)
    limit = _limit(spec, limits)
    statement = dialect.limited_select(join(", ", items), body, limit + 1)
    return Compiled(statement, tuple(names), table, limit, tuple(notes))
