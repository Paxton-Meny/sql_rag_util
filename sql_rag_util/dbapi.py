"""The part of PEP 249 the package relies on, as structural types.

Any driver's connection satisfies :class:`Connection` without importing
anything from this package; the types exist so signatures say what they use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["Connection", "Cursor"]


class Cursor(Protocol):
    """A PEP 249 cursor: execute one statement, fetch its rows, close."""

    def execute(self, operation: str, parameters: Any, /) -> object:
        """Run ``operation`` with bound ``parameters``."""

    def fetchall(self) -> Iterable[Any]:
        """Return every remaining row."""

    def fetchmany(self, size: int, /) -> Iterable[Any]:
        """Return up to ``size`` rows."""

    def close(self) -> object:
        """Release the cursor."""


class Connection(Protocol):
    """A PEP 249 connection. The package only ever asks it for cursors."""

    def cursor(self) -> Cursor:
        """Return a new cursor."""
