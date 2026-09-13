"""Tests for strategy selection and the search predicate."""

from __future__ import annotations

import unittest

from sql_rag_util.dialects import load
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.exceptions import CapabilityError
from sql_rag_util.search.strategies import SearchColumn, Strategy, available_strategies, default_strategies, search_where
from sql_rag_util.sql.render import render


class StrategyTest(unittest.TestCase):
    """Availability follows capabilities; predicates OR across columns and strategies."""

    def test_availability(self) -> None:
        """Base strategies are always available; fuzzy ones need their capability."""
        self.assertEqual(available_strategies(()), (Strategy.EXACT, Strategy.PREFIX, Strategy.CONTAINS))
        self.assertEqual(default_strategies(()), (Strategy.CONTAINS,))
        self.assertEqual(default_strategies({Capability.SOUNDEX, Capability.TRIGRAM}), (Strategy.CONTAINS, Strategy.SOUNDEX, Strategy.TRIGRAM))

    def test_predicate_shape(self) -> None:
        """Tokens AND together; within a token, columns and strategies OR; short tokens skip fuzzy."""
        dialect = load("sqlite")
        columns = (SearchColumn("first", '"t0"."first"'), SearchColumn("last", '"t0"."last"'))
        statement = search_where(dialect, {Capability.SOUNDEX}, columns, ("Jon", "Smyth"), (Strategy.CONTAINS, Strategy.SOUNDEX))
        text, params = render(statement, "qmark")
        self.assertEqual(text.count(" AND "), 1)
        self.assertEqual(text.count("sqlrag_soundex_any("), 4)
        self.assertEqual(params[:2], ("%Jon%", "Jon"))
        short = search_where(dialect, {Capability.SOUNDEX}, columns, ("ab",), (Strategy.SOUNDEX,))
        self.assertNotIn("sqlrag_soundex_any", render(short, "qmark")[0])
        self.assertIn("LIKE", render(short, "qmark")[0])
        either = search_where(dialect, (), columns, ("a1", "b2"), (Strategy.EXACT,), match_all=False)
        self.assertIn(") OR (", render(either, "qmark")[0])

    def test_fulltext_only_on_flagged_columns_and_refusals(self) -> None:
        """FREETEXT applies only where flagged; an unavailable strategy is refused with the allowed list."""
        dialect = load("mssql")
        columns = (SearchColumn("a", "[t0].[a]", fulltext=True), SearchColumn("b", "[t0].[b]"))
        text, _ = render(search_where(dialect, {Capability.FULLTEXT}, columns, ("word",), (Strategy.FULLTEXT,)), "qmark")
        self.assertEqual(text.count("FREETEXT("), 1)
        with self.assertRaises(CapabilityError) as ctx:
            search_where(dialect, (), columns, ("word",), (Strategy.TRIGRAM,))
        self.assertIn(Strategy.CONTAINS, ctx.exception.suggestions)


if __name__ == "__main__":
    unittest.main()
