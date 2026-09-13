"""End-to-end tests of the built-in tools through the engine."""

from __future__ import annotations

import pathlib
import unittest

from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from tests.support.fixture import build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


class ToolsTest(unittest.TestCase):
    """query, describe_table, and list_tables through dispatch."""

    def setUp(self) -> None:
        conn = build_fixture()
        self.addCleanup(conn.close)
        self.engine = SqlRag(conn, metadata_root=FIXTURES, config=Config(reveal_sql=True))

    def test_tool_specs_by_tier(self) -> None:
        """minimal exposes query only; standard adds describe and list; schemas derive."""
        self.assertEqual([s.name for s in self.engine.tool_specs(tier="minimal")], ["query"])
        self.assertEqual([s.name for s in self.engine.tool_specs()], ["query", "describe_table", "list_tables"])
        for spec in self.engine.tool_specs():
            with self.subTest(tool=spec.name):
                self.assertEqual(spec.input_schema()["type"], "object")
                self.assertTrue(spec.examples)

    def test_query_idioms(self) -> None:
        """Rows, count, distinct, join, concept, named measure, and empty results."""
        rows = self.engine.dispatch("query", {"table": "orders", "columns": ["id", "customer.name"], "filters": [{"column": "status", "op": "eq", "value": "open"}]})
        self.assertEqual((rows["columns"], rows["rows"], rows["row_count"], rows["truncated"]), (["id", "customer.name"], [[10, "Acme Corp"]], 1, False))
        self.assertIn("SELECT", rows["sql"])
        count = self.engine.dispatch("query", {"table": "orders", "measures": [{"fn": "count"}], "concepts": ["active"]})
        self.assertEqual(count["rows"], [[2]])
        distinct = self.engine.dispatch("query", {"table": "orders", "group_by": ["status"], "measures": [{"fn": "count"}]})
        self.assertEqual(len(distinct["rows"]), 4)
        revenue = self.engine.dispatch("query", {"table": "orders", "group_by": ["customer.region"], "measures": [{"fn": "measure", "column": "revenue"}]})
        self.assertEqual((revenue["columns"], revenue["rows"][0]), (["customer.region", "revenue"], ["north", 269.99]))
        empty = self.engine.dispatch("query", {"table": "orders", "filters": [{"column": "status", "op": "eq", "value": "opne"}]})
        self.assertEqual(empty["rows"], [])
        self.assertTrue(empty["notes"][0].startswith("0 rows"))
        text = self.engine.dispatch_text("query", {"table": "orders", "columns": ["id", "status"], "limit": 2})
        self.assertTrue(text.startswith("id\tstatus\n10\topen\n11\tpaid\nnote: result truncated"))

    def test_query_errors_carry_suggestions(self) -> None:
        """Unknown tables, concepts, measures, and hidden columns come back as error envelopes."""
        self.assertEqual(self.engine.dispatch("query", {"table": "ordr"})["error"]["suggestions"], ["orders"])
        self.assertEqual(self.engine.dispatch("query", {"table": "orders", "concepts": ["archived"]})["error"]["type"], "UnknownConceptError")
        self.assertEqual(self.engine.dispatch("query", {"table": "orders", "measures": [{"fn": "measure", "column": "profit"}]})["error"]["suggestions"], ["revenue", "order_count"])
        self.assertEqual(self.engine.dispatch("query", {"table": "orders", "columns": ["notes"]})["error"]["type"], "SensitiveColumnError")
        self.assertEqual(self.engine.dispatch("query", {"table": "customers", "filters": [{"column": "email", "op": "eq", "value": "x"}]})["error"]["type"], "SensitiveColumnError")

    def test_describe_and_list(self) -> None:
        """describe_table returns the card; list_tables one summary per table."""
        card = self.engine.dispatch("describe_table", {"table": "Orders"})
        self.assertEqual(card["table"], "orders")
        self.assertEqual(card["schema_version"], self.engine.schema_version)
        self.assertTrue(self.engine.dispatch_text("describe_table", {"table": "orders"}).startswith("# orders"))
        listing = self.engine.dispatch("list_tables", {})
        self.assertEqual([t["table"] for t in listing["tables"]], ["customers", "employees", "orders", "shipment_events", "shipments"])
        self.assertIn("orders (6 cols): One row per customer order.", self.engine.dispatch_text("list_tables", {}))

    def test_scope_is_invisible_and_applied(self) -> None:
        """A developer scope filter narrows every query on its table."""
        conn = build_fixture()
        self.addCleanup(conn.close)
        scoped = SqlRag(conn, metadata_root=FIXTURES, config=Config(scope=lambda t: ({"column": "region", "op": "eq", "value": "north"},) if t == "customers" else ()))
        self.assertEqual(scoped.dispatch("query", {"table": "customers", "measures": [{"fn": "count"}]})["rows"], [[2]])


if __name__ == "__main__":
    unittest.main()
