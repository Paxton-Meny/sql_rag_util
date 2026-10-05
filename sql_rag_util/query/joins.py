"""Resolve dotted column paths into joins along declared relationships."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import LimitExceededError
from sql_rag_util.schema.resolve import resolve_column, resolve_relationship
from sql_rag_util.sql.statement import Statement, join, sql

if TYPE_CHECKING:
    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.query.policy import ColumnPolicy
    from sql_rag_util.schema.model import Catalog, ColumnInfo, Relationship, TableInfo

__all__ = ["JoinStep", "ResolvedColumn", "JoinPlan"]

_BASE_ALIAS = "t0"


@dataclass(frozen=True, slots=True)
class JoinStep:
    """One join reached through a relationship from a parent alias."""

    alias: str
    parent_alias: str
    relationship: Relationship
    table: TableInfo


@dataclass(frozen=True, slots=True)
class ResolvedColumn:
    """A column path resolved to an alias and a catalog column."""

    path: str
    alias: str
    table: TableInfo
    column: ColumnInfo


@dataclass(slots=True)
class JoinPlan:
    """Accumulates the joins a spec needs while resolving its paths.

    Parameters
    ----------
    catalog
        The catalog paths resolve against.
    policy
        Column visibility rules.
    base
        The table the spec reads from.
    max_depth
        Maximum relationship hops in one path.
    full
        The catalog with hidden columns kept, for trusted resolution.
    """

    catalog: Catalog
    policy: ColumnPolicy
    base: TableInfo
    max_depth: int
    steps: dict[str, JoinStep] = field(default_factory=dict)
    full: Catalog | None = None

    @property
    def base_alias(self) -> str:
        """Return the alias of the base table."""
        return _BASE_ALIAS

    @property
    def fans_out(self) -> bool:
        """Return whether any join can multiply base rows."""
        return any(s.relationship.cardinality == "to_many" for s in self.steps.values())

    def resolve(self, path: str, *, trusted: bool = False) -> ResolvedColumn:
        """Resolve ``path`` such as ``customer.region.name``, adding joins as needed.

        A ``trusted`` path resolves its column against the full catalog and
        skips the column policy, so it may name a hidden or sensitive column.
        Only developer scope filters are trusted; nothing an agent supplies is.
        """
        parts = path.split(".")
        hops, column_name = parts[:-1], parts[-1]
        if len(hops) > self.max_depth:
            raise LimitExceededError(f"path {path!r} exceeds the join depth of {self.max_depth}")
        alias, table = _BASE_ALIAS, self.base
        prefix = ""
        for hop in hops:
            relationship = resolve_relationship(self.catalog, table, hop)
            prefix = f"{prefix}.{hop}" if prefix else hop
            step = self.steps.get(prefix)
            if step is None:
                target = self.catalog.table(relationship.target)
                if target is None:
                    raise LimitExceededError(f"relationship {hop!r} targets a table outside the catalog")
                step = JoinStep(f"t{len(self.steps) + 1}", alias, relationship, target)
                self.steps[prefix] = step
            alias, table = step.alias, step.table
        if trusted:
            return ResolvedColumn(path, alias, table, resolve_column((self.full or self.catalog).require(table.ref), column_name))
        column = resolve_column(table, column_name)
        self.policy.check_usable(table.ref, column.name)
        return ResolvedColumn(path, alias, table, column)

    def column_sql(self, dialect: Dialect, resolved: ResolvedColumn) -> str:
        """Return the quoted ``alias.column`` reference."""
        return f"{dialect.quote(resolved.alias)}.{dialect.quote(resolved.column.name)}"

    def from_clause(self, dialect: Dialect) -> Statement:
        """Return ``FROM base AS t0`` followed by one LEFT JOIN per step."""
        clauses = [sql(f"FROM {dialect.qualify(self.base.ref)} AS {dialect.quote(_BASE_ALIAS)}")]
        for step in self.steps.values():
            conditions = [
                f"{dialect.quote(step.parent_alias)}.{dialect.quote(src)} = {dialect.quote(step.alias)}.{dialect.quote(dst)}"
                for src, dst in step.relationship.pairs
            ]
            clauses.append(
                sql(f"LEFT JOIN {dialect.qualify(step.table.ref)} AS {dialect.quote(step.alias)} ON {' AND '.join(conditions)}")
            )
        return join(" ", clauses)
