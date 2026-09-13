"""The only place that executes a statement against the connection.

Every command renders through :func:`~sql_rag_util.sql.render.render`,
executes here, fetches a bounded number of rows, closes the cursor, and
never commits. The audit hook fires after every execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sql_rag_util.config import StatementEvent
from sql_rag_util.exceptions import ExecutionError
from sql_rag_util.sql.render import render

if TYPE_CHECKING:
    from collections.abc import Callable

    from sql_rag_util.sql.statement import Statement

__all__ = ["Fetched", "Executor"]


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
        connection: object,
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
        ``None`` fetches everything, which only introspection should do.

        Raises
        ------
        ExecutionError
            Wrapping whatever the driver raised, with the statement text.
        """
        text, params = render(statement, self._paramstyle)
        cursor = self._connection.cursor()  # type: ignore[attr-defined]
        started = time.perf_counter()
        try:
            cursor.execute(text, params)
            if limit is None:
                raw = list(cursor.fetchall())
            else:
                raw = list(cursor.fetchmany(limit + 1))
        except Exception as exc:
            raise ExecutionError(f"{command}: {type(exc).__name__}: {exc}") from exc
        finally:
            cursor.close()
        elapsed = time.perf_counter() - started
        truncated = limit is not None and len(raw) > limit
        rows = tuple(tuple(r) for r in (raw[:limit] if truncated else raw))
        if self._on_statement is not None:
            self._on_statement(StatementEvent(command, text, len(params), elapsed, len(rows)))
        return Fetched(rows, truncated)
