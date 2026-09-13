"""A statement is a sequence of SQL fragments and bound values.

Builders assemble :class:`Statement` objects and never see a paramstyle.
See ``docs/design/statement-parts-not-placeholder-translation.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import StatementError

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["Bind", "Statement", "sql", "bind", "join"]

_COLLECTION_TYPES = (list, tuple, set, frozenset, dict)


@dataclass(frozen=True, slots=True)
class Bind:
    """A value to bind as a parameter.

    Parameters
    ----------
    value
        A scalar the driver can bind. Collections are refused so that an IN
        list is always expanded into one placeholder per value.
    """

    value: object

    def __post_init__(self) -> None:
        if isinstance(self.value, _COLLECTION_TYPES):
            raise StatementError(f"cannot bind a {type(self.value).__name__}; bind each value")


@dataclass(frozen=True, slots=True)
class Statement:
    """An ordered sequence of text fragments and :class:`Bind` values.

    Parameters
    ----------
    parts
        Fragments and binds in emission order.
    """

    parts: tuple[str | Bind, ...] = ()

    def __add__(self, other: Statement) -> Statement:
        """Concatenate two statements without a separator."""
        return Statement(self.parts + other.parts)

    @property
    def is_empty(self) -> bool:
        """Return whether the statement has no text and no binds."""
        return not any(part for part in self.parts)

    @property
    def binds(self) -> tuple[Bind, ...]:
        """Return the bound values in emission order."""
        return tuple(part for part in self.parts if isinstance(part, Bind))

    @property
    def text_preview(self) -> str:
        """Return the fragments joined with ``?`` in place of each bind, for tests and logs."""
        return "".join("?" if isinstance(part, Bind) else part for part in self.parts)


def sql(text: str) -> Statement:
    """Return a statement holding one text fragment."""
    return Statement((text,))


def bind(value: object) -> Statement:
    """Return a statement holding one bound value."""
    return Statement((Bind(value),))


def join(separator: str, statements: Iterable[Statement]) -> Statement:
    """Concatenate ``statements`` with ``separator`` text between each pair."""
    parts: list[str | Bind] = []
    for index, statement in enumerate(statements):
        if index:
            parts.append(separator)
        parts.extend(statement.parts)
    return Statement(tuple(parts))
