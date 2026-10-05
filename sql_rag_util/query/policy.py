"""Which columns an agent may see or use, as derived from metadata flags."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sql_rag_util.exceptions import SensitiveColumnError, UnknownColumnError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sql_rag_util.schema.model import ColumnInfo, TableRef

__all__ = ["ColumnPolicy"]


@dataclass(frozen=True, slots=True)
class ColumnPolicy:
    """Hidden and sensitive column names per table.

    Hidden columns do not exist to the agent. Sensitive columns are named
    in descriptions but refused in every statement position.
    """

    hidden: Mapping[TableRef, frozenset[str]] = field(default_factory=dict)
    sensitive: Mapping[TableRef, frozenset[str]] = field(default_factory=dict)

    def is_hidden(self, ref: TableRef, column: str) -> bool:
        """Return whether ``column`` of ``ref`` is hidden."""
        return column in self.hidden.get(ref, frozenset())

    def is_sensitive(self, ref: TableRef, column: str) -> bool:
        """Return whether ``column`` of ``ref`` is sensitive."""
        return column in self.sensitive.get(ref, frozenset())

    def check_usable(self, ref: TableRef, column: str) -> None:
        """Raise unless ``column`` may appear in a statement.

        A hidden column raises the same error a missing column does, so the
        agent cannot tell the two apart.
        """
        if self.is_hidden(ref, column):
            raise UnknownColumnError(f"unknown column {column!r} on table {ref.qualified}")
        if self.is_sensitive(ref, column):
            raise SensitiveColumnError(f"column {column!r} on {ref.qualified} is sensitive and cannot be used")

    def visible(self, ref: TableRef, columns: tuple[ColumnInfo, ...]) -> tuple[ColumnInfo, ...]:
        """Return the columns an agent may see: everything but hidden ones."""
        return tuple(c for c in columns if not self.is_hidden(ref, c.name))

    def selectable(self, ref: TableRef, columns: tuple[ColumnInfo, ...]) -> tuple[ColumnInfo, ...]:
        """Return the columns a statement may select: neither hidden nor sensitive."""
        return tuple(c for c in self.visible(ref, columns) if not self.is_sensitive(ref, c.name))
