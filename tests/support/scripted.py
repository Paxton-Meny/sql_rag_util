"""A scripted PEP 249 driver that answers statements by rule and checks every bind.

Each statement is matched against the rules in order; the first whose pattern
is found answers it with rows or an error. A statement no rule matches, or one
whose placeholders disagree with its parameters under the driver's
paramstyle, is recorded as a violation and raised, so a test can fail on
either even when the package wraps the exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.support.fakes import register_driver

if TYPE_CHECKING:
    import unittest
    from collections.abc import Callable, Sequence

__all__ = ["Rule", "ScriptError", "ScriptedConnection", "ScriptedCursor", "placeholders", "scripted_driver"]

_PERCENT = re.compile(r"%(%|s|\(([A-Za-z_][A-Za-z0-9_]*)\)s)?")
_COLON = re.compile(r":([A-Za-z_][A-Za-z0-9_]*|[0-9]+)")
_QUOTES = {"'": "'", '"': '"', "[": "]"}


class ScriptError(AssertionError):
    """A statement was unscripted or its binds did not match its placeholders."""


@dataclass(frozen=True)
class Rule:
    """One scripted answer.

    Parameters
    ----------
    pattern
        Regular expression searched for in the statement text.
    rows
        The rows to return, or a function of ``(text, parameters)`` returning them.
    error
        An exception to raise instead of answering.
    """

    pattern: str
    rows: Sequence[tuple[object, ...]] | Callable[[str, Any], Sequence[tuple[object, ...]]] = ()
    error: Exception | None = None

    def answer(self, text: str, parameters: Any) -> list[tuple[object, ...]]:
        """Return the rows for ``text``, or raise the scripted error."""
        if self.error is not None:
            raise self.error
        return list(self.rows(text, parameters) if callable(self.rows) else self.rows)


def _outside_quotes(text: str) -> str:
    out, closing = [], None
    for char in text:
        if closing is not None:
            closing = None if char == closing else closing
            out.append(" ")
        elif char in _QUOTES:
            closing = _QUOTES[char]
            out.append(" ")
        else:
            out.append(char)
    return "".join(out)


def placeholders(text: str, paramstyle: str) -> list[str]:
    """Return the placeholders in ``text``, in order, as the driver would read them.

    ``format`` and ``pyformat`` drivers interpolate across the whole text, so a
    ``%`` that is neither ``%%`` nor a placeholder is an error even inside a
    string literal. The other styles ignore quoted literals and identifiers.

    Raises
    ------
    ScriptError
        For a stray ``%`` under a percent style, or an unknown paramstyle.
    """
    if paramstyle in ("format", "pyformat"):
        found = []
        for match in _PERCENT.finditer(text):
            token = match.group(1)
            if token is None or (paramstyle == "format") != (token == "s") and token != "%":
                raise ScriptError(f"stray {match.group(0)!r} for {paramstyle} in {text!r}")
            if token != "%":
                found.append(match.group(2) or "s")
        return found
    plain = _outside_quotes(text)
    if paramstyle == "qmark":
        return ["?"] * plain.count("?")
    if paramstyle in ("named", "numeric"):
        return [m.group(1) for m in _COLON.finditer(plain)]
    raise ScriptError(f"unknown paramstyle {paramstyle!r}")


def _expected(parameters: Any, paramstyle: str) -> list[str]:
    if paramstyle in ("pyformat", "named"):
        return sorted(parameters)
    if paramstyle == "numeric":
        return [str(i) for i in range(1, len(parameters) + 1)]
    return [{"qmark": "?", "format": "s"}[paramstyle]] * len(parameters)


class ScriptedCursor:
    """A cursor of :class:`ScriptedConnection`."""

    def __init__(self, connection: ScriptedConnection) -> None:
        self._connection = connection
        self._rows: list[Any] = []
        self.closed = False

    def execute(self, operation: str, parameters: Any = (), /) -> None:
        """Check the binds, find the rule, and queue its rows."""
        rows = self._connection.answer(operation, parameters)
        self._rows = [dict(zip((f"c{i}" for i in range(len(r))), r, strict=True)) for r in rows] if self._connection.dict_rows else rows

    def fetchall(self) -> list[Any]:
        """Return every remaining row."""
        out, self._rows = self._rows, []
        return out

    def fetchmany(self, size: int, /) -> list[Any]:
        """Return up to ``size`` rows."""
        out, self._rows = self._rows[:size], self._rows[size:]
        return out

    def close(self) -> None:
        """Mark the cursor closed."""
        self.closed = True


@dataclass
class ScriptedConnection:
    """A connection that answers from ``rules`` and records everything it sees.

    Parameters
    ----------
    rules
        Answers, tried in order.
    paramstyle
        How the driver reads placeholders.
    dict_rows
        Return rows as mappings, as some drivers can be configured to.
    """

    rules: list[Rule]
    paramstyle: str = "qmark"
    dict_rows: bool = False
    executed: list[tuple[str, Any]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    cursors: list[ScriptedCursor] = field(default_factory=list)
    commits: int = 0

    def cursor(self) -> ScriptedCursor:
        """Return a new cursor."""
        cursor = ScriptedCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        """Record a commit, which the package must never call."""
        self.commits += 1

    def answer(self, text: str, parameters: Any) -> list[tuple[object, ...]]:
        """Record ``text``, check its binds, and return the first matching rule's rows."""
        self.executed.append((text, parameters))
        try:
            found = placeholders(text, self.paramstyle)
            if sorted(found) != sorted(_expected(parameters, self.paramstyle)):
                raise ScriptError(f"placeholders {found} do not match parameters {parameters!r} in {text!r}")
            rule = next((r for r in self.rules if re.search(r.pattern, text)), None)
            if rule is None:
                raise ScriptError(f"unscripted statement {text!r}")
        except ScriptError as exc:
            self.violations.append(str(exc))
            raise
        return rule.answer(text, parameters)

    @property
    def all_closed(self) -> bool:
        """Return whether every cursor handed out has been closed."""
        return all(c.closed for c in self.cursors)


def scripted_driver(test: unittest.TestCase, name: str, paramstyle: str) -> type[ScriptedConnection]:
    """Register a driver module called ``name`` until ``test`` ends and return its scripted connection class."""
    register_driver(test, name, paramstyle)
    return type("Connection", (ScriptedConnection,), {"__module__": f"{name}.connections"})
