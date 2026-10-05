"""End-to-end tests of search_rows."""

from __future__ import annotations

import unittest

from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from sql_rag_util.search.sqlite_functions import register_sqlite_functions
from tests.support.fixture import FIXTURES, build_fixture



class SearchRowsTest(unittest.TestCase):
    """Misspelled names find rows once fuzzy functions are registered."""

    def setUp(self) -> None:
        self.conn = build_fixture()
        self.addCleanup(self.conn.close)
        register_sqlite_functions(self.conn)
        self.engine = SqlRag(self.conn, metadata_root=FIXTURES, config=Config(reveal_sql=True))

    def test_fuzzy_name(self) -> None:
        """A misspelled name matches through Soundex and Levenshtein on the searchable column."""
        result = self.engine.dispatch("search_rows", {"table": "customers", "term": "John Smith"})
        self.assertEqual([r[1] for r in result["rows"]], ["Jon Smyth"])
        self.assertEqual(result["searched"], ["name"])
        self.assertIn("soundex", result["strategies"])
        self.assertIn("levenshtein", result["strategies"])
        self.assertNotIn("email", result["columns"])

    def test_options_and_errors(self) -> None:
        """match any widens; unknown columns, unsearchable tables, and empty terms are errors."""
        result = self.engine.dispatch("search_rows", {"table": "customers", "term": "acme zeta", "match": "any", "strategies": ["contains"]})
        self.assertEqual(sorted(r[1] for r in result["rows"]), ["Acme Corp", "Zeta Ltd"])
        self.assertEqual(self.engine.dispatch("search_rows", {"table": "customers", "term": "x", "columns": ["region"]})["error"]["type"], "QuerySpecError")
        self.assertEqual(self.engine.dispatch("search_rows", {"table": "orders", "term": "open"})["error"]["type"], "QuerySpecError")
        self.assertEqual(self.engine.dispatch("search_rows", {"table": "customers", "term": "   "})["error"]["type"], "QuerySpecError")
        self.assertEqual(self.engine.dispatch("search_rows", {"table": "customers", "term": "x", "strategies": ["trigram"]})["error"]["type"], "CapabilityError")
        empty = self.engine.dispatch("search_rows", {"table": "customers", "term": "nobody"})
        self.assertEqual(empty["rows"], [])
        self.assertTrue(empty["notes"][0].startswith("0 rows"))
        text = self.engine.dispatch_text("search_rows", {"table": "customers", "term": "acme"})
        self.assertTrue(text.startswith("id\tname\tregion\n1\tAcme Corp\tnorth"))


if __name__ == "__main__":
    unittest.main()
