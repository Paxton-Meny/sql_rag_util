"""Measure expressions for grouped queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_rag_util.exceptions import QuerySpecError
from sql_rag_util.query.spec import AggregateFn
from sql_rag_util.schema.model import NUMERIC_KINDS, ColumnKind
from sql_rag_util.sql.statement import Statement, sql

if TYPE_CHECKING:
    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.query.joins import JoinPlan
    from sql_rag_util.query.spec import Measure

__all__ = ["measure_sql"]

_ORDERED_KINDS = NUMERIC_KINDS | {ColumnKind.TEXT, ColumnKind.DATE, ColumnKind.TIME, ColumnKind.DATETIME}
_FUNCTION_TEXT = {
    AggregateFn.COUNT: "COUNT",
    AggregateFn.COUNT_DISTINCT: "COUNT",
    AggregateFn.SUM: "SUM",
    AggregateFn.AVG: "AVG",
    AggregateFn.MIN: "MIN",
    AggregateFn.MAX: "MAX",
}


def measure_sql(dialect: Dialect, plan: JoinPlan, measure: Measure) -> Statement:
    """Return ``FN(column) AS alias`` for ``measure``, with kind gates applied."""
    if measure.fn is AggregateFn.MEASURE:
        raise QuerySpecError(f"named measure {measure.column!r} was not expanded")
    alias = dialect.quote(measure.name)
    if measure.column is None:
        return sql(f"COUNT(*) AS {alias}")
    resolved = plan.resolve(measure.column)
    kind = resolved.column.kind
    if measure.fn in (AggregateFn.SUM, AggregateFn.AVG) and kind not in NUMERIC_KINDS:
        raise QuerySpecError(f"{measure.fn} needs a numeric column; {measure.column!r} is {kind}")
    if measure.fn in (AggregateFn.MIN, AggregateFn.MAX) and kind not in _ORDERED_KINDS:
        raise QuerySpecError(f"{measure.fn} is not defined for {kind} column {measure.column!r}")
    inner = plan.column_sql(dialect, resolved)
    if measure.fn is AggregateFn.COUNT_DISTINCT:
        inner = f"DISTINCT {inner}"
    return sql(f"{_FUNCTION_TEXT[measure.fn]}({inner}) AS {alias}")
