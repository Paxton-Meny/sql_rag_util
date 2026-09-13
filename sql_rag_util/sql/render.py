"""Render a :class:`~sql_rag_util.sql.statement.Statement` for a driver paramstyle.

This is the only place that knows what a placeholder looks like. Fragments
are emitted verbatim except that ``%`` is doubled for the format styles,
where the driver interprets it.
"""

from __future__ import annotations

from sql_rag_util.exceptions import StatementError
from sql_rag_util.sql.statement import Bind, Statement

__all__ = ["PARAMSTYLES", "Rendered", "render"]

PARAMSTYLES: frozenset[str] = frozenset({"qmark", "format", "pyformat", "named", "numeric"})
_PERCENT_STYLES: frozenset[str] = frozenset({"format", "pyformat"})
_PARAMETER_PREFIX = "p"

Rendered = tuple[str, tuple[object, ...] | dict[str, object]]


def _placeholder(paramstyle: str, index: int) -> str:
    if paramstyle == "qmark":
        return "?"
    if paramstyle == "format":
        return "%s"
    if paramstyle == "pyformat":
        return f"%({_PARAMETER_PREFIX}{index})s"
    if paramstyle == "named":
        return f":{_PARAMETER_PREFIX}{index}"
    return f":{index + 1}"


def render(statement: Statement, paramstyle: str) -> Rendered:
    """Return the SQL text and parameters for ``statement`` under ``paramstyle``.

    Parameters
    ----------
    statement
        The statement to render.
    paramstyle
        One of :data:`PARAMSTYLES`, as the driver module reports.

    Returns
    -------
    tuple
        The text, and a tuple of values for positional styles or a dict for
        the named styles.

    Raises
    ------
    StatementError
        When the paramstyle is unknown or the statement is empty.
    """
    if paramstyle not in PARAMSTYLES:
        raise StatementError(f"unknown paramstyle {paramstyle!r}; expected one of {sorted(PARAMSTYLES)}")
    if statement.is_empty:
        raise StatementError("cannot render an empty statement")
    pieces: list[str] = []
    values: list[object] = []
    for part in statement.parts:
        if isinstance(part, Bind):
            pieces.append(_placeholder(paramstyle, len(values)))
            values.append(part.value)
        elif paramstyle in _PERCENT_STYLES:
            pieces.append(part.replace("%", "%%"))
        else:
            pieces.append(part)
    text = "".join(pieces)
    if paramstyle in {"pyformat", "named"}:
        return text, {f"{_PARAMETER_PREFIX}{i}": v for i, v in enumerate(values)}
    return text, tuple(values)
