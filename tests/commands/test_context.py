"""End-to-end tests of get_context and empty-result diagnosis."""

from __future__ import annotations

import unittest
from collections.abc import Sequence

from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from tests.support.fixture import build_fixture, fixture_connection, writable_metadata



class GetContextTest(unittest.TestCase):
    """Questions rank the right tables, link literals to columns, and stay within budget."""

    def setUp(self) -> None:
        self.root = writable_metadata(self)
        self.engine = SqlRag(fixture_connection(self), metadata_root=self.root)

    def test_question_about_orders_for_acme(self) -> None:
        """orders and customers lead, Acme links to customers.name, open links to orders.status."""
        result = self.engine.dispatch("get_context", {"question": "Which open orders does Acme Corp have?"})
        tables = [c["table"] for c in result["tables"]]
        self.assertEqual(set(tables[:2]), {"orders", "customers"})
        hits = {(h["column"], h["value"]) for h in result["value_hits"]}
        self.assertIn(("name", "Acme Corp"), hits)
        self.assertIn(("status", "open"), hits)
        self.assertLessEqual(result["used_tokens"], 1500)
        self.assertEqual(result["schema_version"], self.engine.schema_version)
        self.assertTrue((self.root / ".cache" / "values.json").is_file())
        text = self.engine.dispatch_text("get_context", {"question": "open orders for acme", "format": "compact"})
        self.assertTrue(text.startswith("# orders") or text.startswith("# customers"))
        self.assertIn("values: ", text)

    def test_budget_and_glossary(self) -> None:
        """A tight budget demotes tables to summaries; glossary terms match on synonyms."""
        result = self.engine.dispatch("get_context", {"question": "product code for a shipment", "budget_tokens": 120})
        self.assertLessEqual(len(result["tables"]), 1)
        self.assertLessEqual(result["used_tokens"], 120)
        self.assertEqual([g["term"] for g in result["glossary"]], ["SKU"])
        self.assertEqual(self.engine.dispatch("get_context", {"question": " "})["error"]["type"], "QuerySpecError")
        self.assertEqual(self.engine.dispatch("get_context", {"question": "x", "budget_tokens": 9000})["error"]["type"], "LimitExceededError")

    def test_empty_result_diagnosis(self) -> None:
        """A misspelled status gets the nearest known values in a note."""
        result = self.engine.dispatch("query", {"table": "orders", "filters": [{"column": "status", "op": "eq", "value": "opne"}]})
        self.assertEqual(result["rows"], [])
        self.assertIn("nearest known values: open", result["notes"][0])
        unknown = self.engine.dispatch("query", {"table": "orders", "filters": [{"column": "status", "op": "in", "value": ["zzz"]}]})
        self.assertIn("known values: open, paid, shipped, cancelled", unknown["notes"][0])
        other = build_fixture()
        self.addCleanup(other.close)
        quiet = SqlRag(other, metadata_root=self.root, config=Config(diagnose_empty_results=False))
        plain = quiet.dispatch("query", {"table": "orders", "filters": [{"column": "status", "op": "eq", "value": "opne"}]})
        self.assertTrue(plain["notes"][0].startswith("0 rows"))

    def test_embed_hook_participates(self) -> None:
        """An embed function is called with schema text and its ranking is fused in."""
        calls: list[list[str]] = []

        def embed(texts: Sequence[str]) -> list[list[float]]:
            calls.append(list(texts))
            return [[1.0, 0.0] if "employees" in t else [0.0, 1.0] for t in texts]

        conn = fixture_connection(self)
        engine = SqlRag(conn, config=Config(embed=embed))
        result = engine.dispatch("get_context", {"question": "employees"})
        self.assertEqual(result["tables"][0]["table"], "employees")
        self.assertTrue(calls)
        self.assertFalse(any("Acme" in t for t in calls[0]))

    def test_embed_hook_never_sees_database_values_or_hidden_columns(self) -> None:
        """With metadata and the value index on, the hook gets schema text and the question, nothing read from rows."""
        sent: list[str] = []

        def embed(texts: Sequence[str]) -> list[list[float]]:
            sent.extend(texts)
            return [[1.0, 0.0] for _ in texts]

        engine = SqlRag(fixture_connection(self), metadata_root=self.root, config=Config(embed=embed))
        engine.dispatch("get_context", {"question": "orders for the north region"})
        self.assertTrue((self.root / ".cache" / "values.json").is_file())
        self.assertIn("orders for the north region", sent)
        text = " ".join(sent)
        for leaked in ("Acme Corp", "Jon Smyth", "Zeta Ltd", "UPS", "left depot", "Grace", "rush", "password_hash", "Staff notes"):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, text)


if __name__ == "__main__":
    unittest.main()
