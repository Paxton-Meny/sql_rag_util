"""Fake driver modules, connections, and cursors that record what they receive."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field

from sql_rag_util.dialects.base import Dialect
from sql_rag_util.schema.model import ColumnKind, TableRef
from sql_rag_util.sql.statement import Statement, sql

__all__ = ["FakeCursor", "FakeConnection", "fake_driver", "StubDialect"]


@dataclass
class FakeCursor:
    """Records executed statements and returns canned rows."""

    rows: list[tuple[object, ...]] = field(default_factory=list)
    executed: list[tuple[str, object]] = field(default_factory=list)
    description: tuple[tuple[str, ...], ...] = ()
    closed: bool = False

    def execute(self, sql: str, params: object = ()) -> None:
        """Record the call."""
        self.executed.append((sql, params))

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        """Return up to ``size`` rows and drop them."""
        out, self.rows = self.rows[:size], self.rows[size:]
        return out

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return every remaining row."""
        out, self.rows = self.rows, []
        return out

    def close(self) -> None:
        """Mark the cursor closed."""
        self.closed = True


@dataclass
class FakeConnection:
    """Hands out cursors from a queue and records commits."""

    cursors: list[FakeCursor] = field(default_factory=list)
    commits: int = 0

    def cursor(self) -> FakeCursor:
        """Return the next queued cursor, or a fresh empty one."""
        return self.cursors.pop(0) if self.cursors else FakeCursor()

    def commit(self) -> None:
        """Record a commit, which the package must never call."""
        self.commits += 1


def fake_driver(name: str, paramstyle: str | None) -> type:
    """Register a fake driver module called ``name`` and return a connection class from it."""
    module = types.ModuleType(name)
    if paramstyle is not None:
        module.paramstyle = paramstyle
    sys.modules[name] = module
    cls = type("Connection", (FakeConnection,), {"__module__": f"{name}.connections"})
    return cls



class StubDialect(Dialect):
    """Minimal concrete dialect for tests of the base class."""

    name = "stub"
    default_paramstyle = "qmark"

    def kind_of(self, native_type: str) -> ColumnKind:
        """Classify everything as text."""
        return ColumnKind.TEXT

    def tables_statement(self, schemas: tuple[str, ...] | None) -> Statement:
        """Return a fixed statement."""
        return sql("SELECT name FROM tables")

    def columns_statement(self, ref: TableRef) -> Statement:
        """Return a fixed statement."""
        return sql("SELECT name FROM columns")

    def foreign_keys_statement(self, ref: TableRef) -> Statement:
        """Return a fixed statement."""
        return sql("SELECT name FROM fks")
