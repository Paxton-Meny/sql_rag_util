"""Turn a validated :class:`~sql_rag_util.query.spec.Filter` into a predicate."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import LimitExceededError, QuerySpecError
from sql_rag_util.query.spec import FilterOp
from sql_rag_util.schema.model import NUMERIC_KINDS, TEXT_KINDS, ColumnKind
from sql_rag_util.sql.statement import Statement, bind, join, sql

if TYPE_CHECKING:
    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.query.spec import Filter, JsonScalar
    from sql_rag_util.schema.model import ColumnInfo

__all__ = ["build_predicate", "since_bound"]

_COMPARISON = {
    FilterOp.EQ: "=",
    FilterOp.NE: "<>",
    FilterOp.LT: "<",
    FilterOp.LTE: "<=",
    FilterOp.GT: ">",
    FilterOp.GTE: ">=",
}
_ORDERED_KINDS = NUMERIC_KINDS | {ColumnKind.DATE, ColumnKind.TIME, ColumnKind.DATETIME, ColumnKind.TEXT}
_TEMPORAL_KINDS = frozenset({ColumnKind.DATE, ColumnKind.DATETIME})
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_DATE_FORMAT = "%Y-%m-%d"


def _check_value(column: ColumnInfo, value: JsonScalar) -> JsonScalar:
    kind = column.kind
    if value is None:
        raise QuerySpecError(f"use is_null for column {column.name!r}")
    if kind in NUMERIC_KINDS and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise QuerySpecError(f"column {column.name!r} is numeric; got {value!r}")
    if kind is ColumnKind.BOOLEAN and not isinstance(value, bool):
        raise QuerySpecError(f"column {column.name!r} is boolean; got {value!r}")
    if kind in TEXT_KINDS | _TEMPORAL_KINDS | {ColumnKind.TIME} and not isinstance(value, str):
        raise QuerySpecError(f"column {column.name!r} takes a string; got {value!r}")
    return value


def since_bound(kind: ColumnKind, days: int, *, now: dt.datetime | None = None) -> str:
    """Return the ISO text for ``now`` minus ``days``, shaped for the column kind."""
    moment = (now or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=days)
    return moment.strftime(_DATE_FORMAT if kind is ColumnKind.DATE else _DATETIME_FORMAT)


def build_predicate(
    dialect: Dialect,
    column_sql: str,
    column: ColumnInfo,
    flt: Filter,
    *,
    max_in_values: int,
    now: dt.datetime | None = None,
) -> Statement:
    """Return the predicate for ``flt`` on ``column`` rendered as ``column_sql``.

    Raises
    ------
    QuerySpecError
        When the operator does not fit the column kind or a value has the wrong type.
    LimitExceededError
        When an IN list exceeds ``max_in_values``.
    """
    op = flt.op
    kind = column.kind
    if op in _COMPARISON:
        if op not in (FilterOp.EQ, FilterOp.NE) and kind not in _ORDERED_KINDS:
            raise QuerySpecError(f"{op} is not defined for {kind} column {column.name!r}")
        return sql(f"{column_sql} {_COMPARISON[op]} ") + bind(_check_value(column, flt.value))  # type: ignore[arg-type]
    if op in (FilterOp.IN, FilterOp.NOT_IN):
        values = tuple(_check_value(column, v) for v in flt.value)  # type: ignore[union-attr]
        if len(values) > max_in_values:
            raise LimitExceededError(f"{op} allows at most {max_in_values} values")
        keyword = "IN" if op is FilterOp.IN else "NOT IN"
        return sql(f"{column_sql} {keyword} (") + join(", ", (bind(v) for v in values)) + sql(")")
    if op is FilterOp.BETWEEN:
        if kind not in _ORDERED_KINDS:
            raise QuerySpecError(f"between is not defined for {kind} column {column.name!r}")
        low, high = (_check_value(column, v) for v in flt.value)  # type: ignore[union-attr]
        return sql(f"{column_sql} BETWEEN ") + bind(low) + sql(" AND ") + bind(high)
    if op in (FilterOp.CONTAINS, FilterOp.STARTS_WITH):
        if kind not in TEXT_KINDS:
            raise QuerySpecError(f"{op} needs a text column; {column.name!r} is {kind}")
        text = _check_value(column, flt.value)  # type: ignore[arg-type]
        return dialect.contains(column_sql, text) if op is FilterOp.CONTAINS else dialect.starts_with(column_sql, text)  # type: ignore[arg-type]
    if op is FilterOp.IS_NULL:
        return sql(f"{column_sql} IS NULL")
    if op is FilterOp.NOT_NULL:
        return sql(f"{column_sql} IS NOT NULL")
    if kind not in _TEMPORAL_KINDS:
        raise QuerySpecError(f"since_days needs a date or datetime column; {column.name!r} is {kind}")
    return sql(f"{column_sql} >= ") + bind(since_bound(kind, flt.value, now=now))  # type: ignore[arg-type]
