"""The declarative query spec agents send and builders consume.

Every field is validated on construction so a malformed spec fails before
any catalog lookup or statement building. Names are resolved later against
the catalog; this module checks shape only.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Literal

from sql_rag_util.exceptions import QuerySpecError

__all__ = ["FilterOp", "AggregateFn", "Filter", "Measure", "Order", "QuerySpec", "JsonScalar", "PATH_PATTERN"]

JsonScalar = str | int | float | bool | None
PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_ALIAS_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


class FilterOp(enum.StrEnum):
    """Whitelisted comparison operators."""

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"
    SINCE_DAYS = "since_days"


class AggregateFn(enum.StrEnum):
    """Whitelisted aggregate functions."""

    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    MEASURE = "measure"


_LIST_OPS = frozenset({FilterOp.IN, FilterOp.NOT_IN, FilterOp.BETWEEN})
_NO_VALUE_OPS = frozenset({FilterOp.IS_NULL, FilterOp.NOT_NULL})


def _check_path(path: str, what: str) -> str:
    if not isinstance(path, str) or not PATH_PATTERN.match(path):
        raise QuerySpecError(f"{what} {path!r} is not a column or relationship path")
    return path


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


@dataclass(frozen=True, slots=True)
class Filter:
    """One predicate.

    Parameters
    ----------
    column
        A column name, or a dotted path through relationships.
    op
        The operator.
    value
        A scalar, a list of scalars for ``in``, ``not_in``, and ``between``,
        an integer for ``since_days``, or ``None`` for the null tests.
    """

    column: str = field(metadata={"description": "Column name, or a dotted path through relationships such as customer.region."})
    op: FilterOp = field(metadata={"description": "Operator. contains and starts_with match text case-insensitively where the database allows; since_days keeps rows from the last N days."})
    value: JsonScalar | tuple[JsonScalar, ...] = field(default=None, metadata={"description": "One scalar; a list for in, not_in, and between (two values); an integer for since_days; omitted for is_null and not_null."})

    def __post_init__(self) -> None:
        _check_path(self.column, "filter column")
        try:
            op = FilterOp(self.op)
        except ValueError:
            raise QuerySpecError(f"unknown operator {self.op!r}", suggestions=tuple(FilterOp)) from None
        object.__setattr__(self, "op", op)
        value = self.value
        if isinstance(value, list):
            value = tuple(value)
            object.__setattr__(self, "value", value)
        if op in _NO_VALUE_OPS:
            if value is not None:
                raise QuerySpecError(f"{op} takes no value")
        elif op in _LIST_OPS:
            if not isinstance(value, tuple) or not value or not all(_is_scalar(v) for v in value):
                raise QuerySpecError(f"{op} needs a non-empty list of scalars")
            if op is FilterOp.BETWEEN and len(value) != 2:
                raise QuerySpecError("between needs exactly two values")
        elif op is FilterOp.SINCE_DAYS:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise QuerySpecError("since_days needs a non-negative integer number of days")
        elif not _is_scalar(value) or value is None:
            raise QuerySpecError(f"{op} needs one scalar value")


@dataclass(frozen=True, slots=True)
class Measure:
    """One aggregate.

    Parameters
    ----------
    fn
        The function.
    column
        The column to aggregate; omitted only for ``count``.
    alias
        Result column name; defaults to ``fn`` or ``fn_column``.
    """

    fn: AggregateFn = field(metadata={"description": "Aggregate function, or measure to apply a named measure from describe_table."})
    column: str | None = field(default=None, metadata={"description": "Column or dotted path to aggregate; omit only for count. For fn measure, the measure name."})
    alias: str | None = field(default=None, metadata={"description": "Result name; defaults to fn or fn_column. Use it in order."})

    def __post_init__(self) -> None:
        try:
            fn = AggregateFn(self.fn)
        except ValueError:
            raise QuerySpecError(f"unknown aggregate {self.fn!r}", suggestions=tuple(AggregateFn)) from None
        object.__setattr__(self, "fn", fn)
        if self.column is None and fn is not AggregateFn.COUNT:
            raise QuerySpecError(f"{fn} needs a column" if fn is not AggregateFn.MEASURE else "measure needs the measure name in column")
        if self.column is not None:
            _check_path(self.column, "measure column")
        if self.alias is not None and not _ALIAS_PATTERN.match(self.alias):
            raise QuerySpecError(f"alias {self.alias!r} must be a lowercase identifier")

    @property
    def name(self) -> str:
        """Return the result column name."""
        if self.alias:
            return self.alias
        if self.column is None:
            return str(self.fn)
        return f"{self.fn}_{self.column.replace('.', '_')}"


@dataclass(frozen=True, slots=True)
class Order:
    """One ordering term by column path or measure alias."""

    by: str = field(metadata={"description": "Column path or measure alias to sort by."})
    direction: Literal["asc", "desc"] = field(default="asc", metadata={"description": "asc or desc."})

    def __post_init__(self) -> None:
        _check_path(self.by, "order term")
        if self.direction not in ("asc", "desc"):
            raise QuerySpecError(f"direction must be asc or desc, got {self.direction!r}")


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """A complete read request. See ``docs/agent-tools.md`` for the idioms."""

    table: str = field(metadata={"description": "Table to read, as named by list_tables or get_context."})
    columns: tuple[str, ...] | None = field(default=None, metadata={"description": "Columns to return, bare or dotted through relationships (customer.name joins automatically). Omit for every visible column."})
    filters: tuple[Filter, ...] = field(default=(), metadata={"description": "Predicates AND-ed together."})
    concepts: tuple[str, ...] = field(default=(), metadata={"description": "Named filters from describe_table, AND-ed in."})
    group_by: tuple[str, ...] = field(default=(), metadata={"description": "Columns to group by; returns one row per distinct combination. Cannot combine with columns."})
    measures: tuple[Measure, ...] = field(default=(), metadata={"description": "Aggregates. count alone gives a total; with group_by it gives per-group counts."})
    order: tuple[Order, ...] = field(default=(), metadata={"description": "Sort terms. Default: primary key, or the first measure descending when grouped."})
    limit: int | None = field(default=None, metadata={"description": "Maximum rows; default 50, hard cap 500. Narrow with filters rather than raising it."})
    format: Literal["json", "compact"] = field(default="json", metadata={"description": "json for columns plus rows arrays; compact for a tab-separated text table."})
    names: tuple[str, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        _check_path(self.table, "table")
        for attr in ("columns", "filters", "concepts", "group_by", "measures", "order"):
            value = getattr(self, attr)
            if isinstance(value, list):
                object.__setattr__(self, attr, tuple(value))
        for path in self.columns or ():
            _check_path(path, "column")
        for path in self.group_by:
            _check_path(path, "group_by column")
        for concept in self.concepts:
            if not isinstance(concept, str) or not _ALIAS_PATTERN.match(concept):
                raise QuerySpecError(f"concept {concept!r} must be a lowercase identifier")
        if self.limit is not None and (not isinstance(self.limit, int) or isinstance(self.limit, bool) or self.limit < 1):
            raise QuerySpecError("limit must be a positive integer")
        if self.format not in ("json", "compact"):
            raise QuerySpecError(f"format must be json or compact, got {self.format!r}")
        if self.group_by and self.columns:
            raise QuerySpecError("use group_by without columns; grouped columns are returned automatically")
        if self.measures and not self.group_by and self.columns:
            raise QuerySpecError("measures without group_by return one row; columns cannot be combined with them")
        names = [m.name for m in self.measures]
        if len(set(names)) != len(names):
            raise QuerySpecError(f"measure names must be unique, got {names}")
        object.__setattr__(self, "names", tuple(names))

    @property
    def is_aggregate(self) -> bool:
        """Return whether the spec groups or measures."""
        return bool(self.group_by or self.measures)
