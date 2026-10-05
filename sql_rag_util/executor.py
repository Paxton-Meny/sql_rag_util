"""The only place that executes a statement against the connection.

Every command renders through :func:`~sql_rag_util.sql.render.render`,
executes here, fetches a bounded number of rows, closes the cursor, and
never commits. The audit hook fires after every successful execution.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sql_rag_util.config import StatementEvent
from sql_rag_util.exceptions import ExecutionError
from sql_rag_util.sql.render import render

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from sql_rag_util.dbapi import Connection

    from sql_rag_util.sql.statement import Statement

__all__ = ["Fetched", "Executor"]


@contextlib.contextmanager
def _driver_errors(command: str) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        raise ExecutionError(f"{command}: {type(exc).__name__}: {exc}") from exc


def _values(row: Mapping[object, object] | Iterable[object]) -> tuple[object, ...]:
    return tuple(row.values()) if isinstance(row, Mapping) else tuple(row)


@dataclass(frozen=True, slots=True)
class Fetched:
    """Rows fetched for one statement.

    Parameters
    ----------
    rows
        At most the requested number of rows.
    truncated
        Whether at least one more row existed beyond ``rows``.
    """

    rows: tuple[tuple[object, ...], ...]
    truncated: bool


class Executor:
    """Run statements on one connection with one paramstyle.

    Parameters
    ----------
    connection
        A PEP 249 connection.
    paramstyle
        The paramstyle to render with.
    on_statement
        Audit hook called after every execution, or ``None``.
    """

    def __init__(
        self,
        connection: Connection,
        paramstyle: str,
        *,
        on_statement: Callable[[StatementEvent], None] | None = None,
    ) -> None:
        self._connection = connection
        self._paramstyle = paramstyle
        self._on_statement = on_statement

    @property
    def paramstyle(self) -> str:
        """Return the paramstyle statements are rendered with."""
        return self._paramstyle

    def fetch(self, statement: Statement, *, command: str, limit: int | None = None) -> Fetched:
        """Execute ``statement`` and return up to ``limit`` rows.

        One extra row is requested so ``truncated`` is honest. ``limit`` of
        ``None`` fetches everything, which only introspection should do. Rows
        from cursors that return mappings become tuples of their values.

        Raises
        ------
        ExecutionError
            Wrapping whatever the driver raised while opening, using, or
            closing the cursor, naming the command. When execution fails, a
            failure to close is ignored so the original error is the one raised.
        """
        text, params = render(statement, self._paramstyle)
        started = time.perf_counter()
        with _driver_errors(command):
            cursor = self._connection.cursor()
        try:
            with _driver_errors(command):
                cursor.execute(text, params)
                raw = list(cursor.fetchall()) if limit is None else list(cursor.fetchmany(limit + 1))
        except BaseException:
            with contextlib.suppress(Exception):
                cursor.close()
            raise
        with _driver_errors(command):
            cursor.close()
        elapsed = time.perf_counter() - started
        truncated = limit is not None and len(raw) > limit
        rows = tuple(_values(r) for r in (raw[:limit] if truncated else raw))
        if self._on_statement is not None:
            self._on_statement(StatementEvent(command, text, len(params), elapsed, len(rows)))
        return Fetched(rows, truncated)
