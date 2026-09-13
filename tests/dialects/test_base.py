"""Tests for the dialect contract defaults."""

from __future__ import annotations

import unittest

from sql_rag_util.exceptions import CapabilityError, StatementError
from sql_rag_util.dialects.base import escape_like, kind_from_prefixes
from sql_rag_util.schema.model import ColumnKind, TableRef
from sql_rag_util.sql.render import render
from sql_rag_util.sql.statement import sql
from tests.support.fakes import StubDialect


class BaseDialectTest(unittest.TestCase):
    """Quoting, limits, LIKE escaping, kind mapping, and refusals."""

    def setUp(self) -> None:
        self.dialect = StubDialect()

    def test_quote_doubles_closing_quote_and_rejects_bad_names(self) -> None:
        """Embedded quotes are doubled; empty names and NUL bytes are refused."""
        self.assertEqual(self.dialect.quote('a"b'), '"a""b"')
        self.assertEqual(self.dialect.qualify(TableRef("s", "t")), '"s"."t"')
        self.assertEqual(self.dialect.qualify(TableRef(None, "t")), '"t"')
        for bad in ("", "a\x00b"):
            with self.subTest(bad=bad):
                with self.assertRaises(StatementError):
                    self.dialect.quote(bad)

    def test_limited_select_binds_the_limit(self) -> None:
        """The default limit form is LIMIT with a bound value."""
        statement = self.dialect.limited_select(sql('"a"'), sql('FROM "t"'), 5)
        self.assertEqual(render(statement, "qmark"), ('SELECT "a" FROM "t" LIMIT ?', (5,)))

    def test_like_predicates_escape_metacharacters(self) -> None:
        """Percent, underscore, and the escape character are escaped and the wildcard is added."""
        self.assertEqual(escape_like("50%_a!b"), "50!%!_a!!b")
        contains = self.dialect.contains('"c"', "50%")
        self.assertEqual(render(contains, "qmark"), ('"c" LIKE ? ESCAPE \'!\'', ("%50!%%",)))
        prefix = self.dialect.starts_with('"c"', "ab")
        self.assertEqual(render(prefix, "qmark")[1], ("ab%",))

    def test_kind_from_prefixes(self) -> None:
        """The first matching prefix wins, case-insensitively; no match is OTHER."""
        table = ((("bigint"), ColumnKind.INTEGER), ("int", ColumnKind.INTEGER), ("varchar", ColumnKind.TEXT))
        self.assertEqual(kind_from_prefixes("INT", table), ColumnKind.INTEGER)
        self.assertEqual(kind_from_prefixes("VarChar(20)", table), ColumnKind.TEXT)
        self.assertEqual(kind_from_prefixes("geometry", table), ColumnKind.OTHER)

    def test_fuzzy_predicates_refuse_by_default(self) -> None:
        """A dialect without a capability raises CapabilityError naming itself."""
        calls = (
            lambda: self.dialect.soundex_match('"c"', "x"),
            lambda: self.dialect.difference_at_least('"c"', "x", 3),
            lambda: self.dialect.levenshtein_within('"c"', "x", 2),
            lambda: self.dialect.trigram_at_least('"c"', "x", 0.3),
            lambda: self.dialect.fulltext('"c"', "x"),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(CapabilityError) as ctx:
                    call()
                self.assertIn("stub", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
