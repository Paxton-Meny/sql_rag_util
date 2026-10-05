"""Tests for schema cards."""

from __future__ import annotations

import unittest

from sql_rag_util.engine import SqlRag
from sql_rag_util.retrieval.cards import card_text, summary_text, table_card, table_summary
from sql_rag_util.schema.model import TableRef
from tests.support.fixture import FIXTURES, fixture_connection


class CardsTest(unittest.TestCase):
    """Cards carry keys, flags, values, relationships, concepts, and measures compactly."""

    def setUp(self) -> None:
        conn = fixture_connection(self)
        self.engine = SqlRag(conn, metadata_root=FIXTURES)

    def test_orders_card(self) -> None:
        """Structured and text forms agree and hidden columns are absent."""
        table = self.engine.catalog.table(TableRef(None, "orders"))
        card = table_card(self.engine.annotated, table)
        names = [c["name"] for c in card["columns"]]
        self.assertNotIn("notes", names)
        by_name = {c["name"]: c for c in card["columns"]}
        self.assertEqual(by_name["id"]["key"], "pk")
        self.assertEqual(by_name["customer_id"]["fk"], "customers.id")
        self.assertEqual(by_name["status"]["values"], ["open", "paid", "shipped", "cancelled"])
        self.assertEqual(sorted(r["name"] for r in card["relationships"]), ["customer", "customers_via_billing_customer_id", "order_events", "shipments"])
        self.assertEqual([c["name"] for c in card["concepts"]], ["active", "last_30_days"])
        text = card_text(card)
        self.assertTrue(text.startswith("# orders: One row per customer order.\n"))
        self.assertIn("status TEXT {open,paid,shipped,cancelled}: Lifecycle state.", text)
        self.assertIn("customer_id INTEGER fk->customers.id: The buyer.", text)
        self.assertIn("customer -> customers (to_one): The buyer.", text)
        self.assertIn("concepts: active: Orders that still need attention.", text)
        self.assertIn("measures: revenue: Sum of order amounts.", text)
        self.assertLess(len(text), 900)

    def test_short_card_and_summary(self) -> None:
        """The short form drops prose; summaries are one line."""
        table = self.engine.catalog.table(TableRef(None, "customers"))
        card = table_card(self.engine.annotated, table, full=False)
        self.assertNotIn("description", card)
        text = card_text(card, full=False)
        self.assertIn("email TEXT [sensitive]", text)
        self.assertNotIn("Display name", text)
        self.assertIn("name TEXT [searchable]", text)
        summary = table_summary(self.engine.annotated, table)
        self.assertEqual(summary, {"table": "customers", "purpose": "One row per customer account.", "rows": None, "columns": 4})
        self.assertEqual(summary_text(summary), "customers (4 cols): One row per customer account.")
        self.assertEqual(summary_text({"table": "t", "purpose": "", "rows": 12000, "columns": 2}), "t (~12k rows, 2 cols)")


if __name__ == "__main__":
    unittest.main()
