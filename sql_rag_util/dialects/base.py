"""The dialect contract: quoting, limits, introspection statements, kinds, predicates.

Every difference between databases lives behind this class. Builders call
these methods and never branch on the dialect name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.exceptions import CapabilityError, StatementError
from sql_rag_util.schema.model import ColumnKind
from sql_rag_util.sql.statement import Statement, bind, sql

if TYPE_CHECKING:
    from sql_rag_util.schema.model import TableRef

__all__ = ["Dialect", "LIKE_ESCAPE", "escape_like", "kind_from_prefixes"]

LIKE_ESCAPE = "!"
_LIKE_SPECIALS = ("%", "_", LIKE_ESCAPE)
_FORBIDDEN_IDENTIFIER_CHARS = ("\x00",)


def escape_like(text: str) -> str:
    """Return ``text`` with LIKE metacharacters escaped using :data:`LIKE_ESCAPE`."""
    escaped = text.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
    for special in _LIKE_SPECIALS[:-1]:
        escaped = escaped.replace(special, LIKE_ESCAPE + special)
    return escaped


def kind_from_prefixes(native_type: str, table: tuple[tuple[str, ColumnKind], ...]) -> ColumnKind:
    """Classify ``native_type`` by the first matching prefix in ``table``.

    Parameters
    ----------
    native_type
        The type name the database reports, in any case.
    table
        ``(prefix, kind)`` pairs, checked in order against the folded name.
    """
    folded = native_type.strip().lower()
    for prefix, kind in table:
        if folded.startswith(prefix):
            return kind
    return ColumnKind.OTHER


class Dialect(ABC):
    """Everything that differs between databases.

    Subclasses set the class attributes and implement the abstract methods.
    Fuzzy predicates default to refusing with :class:`CapabilityError`;
    a dialect overrides the ones it supports and lists them in
    ``static_capabilities``.
    """

    name: ClassVar[str]
    default_paramstyle: ClassVar[str]
    quote_open: ClassVar[str] = '"'
    quote_close: ClassVar[str] = '"'
    static_capabilities: ClassVar[frozenset[str]] = frozenset()

    def quote(self, identifier: str) -> str:
        """Return ``identifier`` quoted, with the closing quote doubled inside it."""
        if not identifier or any(c in identifier for c in _FORBIDDEN_IDENTIFIER_CHARS):
            raise StatementError(f"cannot quote identifier {identifier!r}")
        return self.quote_open + identifier.replace(self.quote_close, self.quote_close * 2) + self.quote_close

    def qualify(self, ref: TableRef) -> str:
        """Return the quoted, schema-qualified name of ``ref``."""
        if ref.schema:
            return f"{self.quote(ref.schema)}.{self.quote(ref.name)}"
        return self.quote(ref.name)

    def limited_select(self, select_list: Statement, body: Statement, limit: int) -> Statement:
        """Return ``SELECT <select_list> <body>`` capped at ``limit`` rows with the limit bound."""
        return sql("SELECT ") + select_list + sql(" ") + body + sql(" LIMIT ") + bind(limit)

    def contains(self, column_sql: str, text: str) -> Statement:
        """Return a case-insensitive substring predicate where the dialect allows one."""
        return sql(f"{column_sql} LIKE ") + bind(f"%{escape_like(text)}%") + sql(f" ESCAPE '{LIKE_ESCAPE}'")

    def starts_with(self, column_sql: str, text: str) -> Statement:
        """Return a prefix predicate."""
        return sql(f"{column_sql} LIKE ") + bind(f"{escape_like(text)}%") + sql(f" ESCAPE '{LIKE_ESCAPE}'")

    @abstractmethod
    def kind_of(self, native_type: str) -> ColumnKind:
        """Classify a native type name."""

    @abstractmethod
    def tables_statement(self, schemas: tuple[str, ...] | None) -> Statement:
        """Return a statement yielding ``(schema, name, row_estimate)`` rows."""

    @abstractmethod
    def columns_statement(self, ref: TableRef) -> Statement:
        """Return a statement yielding ``(name, native_type, nullable, pk_position)`` rows."""

    @abstractmethod
    def foreign_keys_statement(self, ref: TableRef) -> Statement:
        """Return a statement yielding ``(constraint, position, column, ref_schema, ref_table, ref_column)`` rows."""

    def capability_probe_statement(self) -> Statement | None:
        """Return a statement yielding one capability name per row, or ``None``."""
        return None

    def _refuse(self, capability: Capability) -> CapabilityError:
        return CapabilityError(f"{self.name} does not support {capability}")

    def soundex_match(self, column_sql: str, text: str) -> Statement:
        """Return a predicate true when the column sounds like ``text``."""
        raise self._refuse(Capability.SOUNDEX)

    def difference_at_least(self, column_sql: str, text: str, threshold: int) -> Statement:
        """Return a predicate on SOUNDEX difference score."""
        raise self._refuse(Capability.DIFFERENCE)

    def levenshtein_within(self, column_sql: str, text: str, distance: int) -> Statement:
        """Return a predicate true within an edit distance."""
        raise self._refuse(Capability.LEVENSHTEIN)

    def trigram_at_least(self, column_sql: str, text: str, threshold: float) -> Statement:
        """Return a predicate on trigram similarity."""
        raise self._refuse(Capability.TRIGRAM)

    def fulltext(self, column_sql: str, text: str) -> Statement:
        """Return a full-text predicate."""
        raise self._refuse(Capability.FULLTEXT)

