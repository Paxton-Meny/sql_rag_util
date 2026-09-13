"""End-to-end tests of the metadata toolkit."""

from __future__ import annotations

import datetime as dt
import pathlib
import shutil
import tempfile
import unittest

from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from tests.support.fixture import build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


class ToolkitTest(unittest.TestCase):
    """Edits validate, write canonically, carry provenance, and refresh the engine."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "meta"
        shutil.copytree(FIXTURES, self.root)
        self.conn = build_fixture()
        self.addCleanup(self.conn.close)
        self.engine = SqlRag(self.conn, metadata_root=self.root, config=Config(allow_metadata_writes=True))

    def test_exposure_requires_writes(self) -> None:
        """Toolkit tools appear only in the full tier with writes enabled."""
        self.assertIn("edit_column", [s.name for s in self.engine.tool_specs(tier="full")])
        self.assertNotIn("edit_column", [s.name for s in self.engine.tool_specs()])
        locked = SqlRag(self.conn, metadata_root=self.root)
        self.assertNotIn("edit_column", [s.name for s in locked.tool_specs(tier="full")])
        self.assertEqual(locked.dispatch("edit_table", {"table": "orders", "purpose": "x"}, tier="full")["error"]["type"], "UnknownToolError")
        nowhere = SqlRag(self.conn, config=Config(allow_metadata_writes=True))
        self.assertEqual(nowhere.dispatch("edit_glossary", {"term": "x", "definition": "y"}, tier="full")["error"]["type"], "ConfigurationError")

    def test_column_edit_with_provenance(self) -> None:
        """A column edit is written with today's date and visible after refresh."""
        version = self.engine.schema_version
        result = self.engine.dispatch("edit_column", {"table": "orders", "column": "amount", "text": "Order total in the customer's currency.", "values": []}, tier="full")
        self.assertEqual(result["changed"], "column amount")
        text = (self.root / "tables" / "orders.md").read_text()
        self.assertIn(f"- amount: Order total in the customer's currency.\n  - source: agent, {dt.date.today().isoformat()}", text)
        self.assertNotEqual(self.engine.schema_version, version)
        card = self.engine.dispatch("describe_table", {"table": "orders"})
        self.assertEqual(next(c for c in card["columns"] if c["name"] == "amount")["text"], "Order total in the customer's currency.")

    def test_new_table_needs_purpose_and_protected_flags_hold(self) -> None:
        """Describing a new table starts with edit_table; sensitive and hidden cannot be made searchable."""
        self.assertEqual(self.engine.dispatch("edit_column", {"table": "shipments", "column": "carrier", "text": "x"}, tier="full")["error"]["type"], "QuerySpecError")
        self.engine.dispatch("edit_table", {"table": "shipments", "purpose": "One row per parcel."}, tier="full")
        ok = self.engine.dispatch("edit_column", {"table": "shipments", "column": "carrier", "text": "Carrier code.", "searchable": True}, tier="full")
        self.assertNotIn("error", ok)
        self.assertTrue((self.root / "tables" / "shipments.md").is_file())
        self.assertIn("carrier", self.engine.annotated.searchable[next(t.ref for t in self.engine.catalog.tables if t.ref.name == "shipments")])
        blocked = self.engine.dispatch("edit_column", {"table": "customers", "column": "email", "text": "x", "searchable": True}, tier="full")
        self.assertEqual(blocked["error"]["type"], "QuerySpecError")
        self.assertIn("[sensitive]", (self.root / "tables" / "customers.md").read_text())

    def test_concept_relationship_glossary_and_validation(self) -> None:
        """Concepts validate through the catalog, relationships must exist, glossary terms replace by name."""
        bad = self.engine.dispatch("edit_concept", {"table": "orders", "name": "big", "text": "x", "where": [{"column": "amount_typo", "op": "gt", "value": 100}]}, tier="full")
        self.assertEqual(bad["error"]["type"], "MetadataFormatError")
        good = self.engine.dispatch("edit_concept", {"table": "orders", "name": "big", "text": "Large orders.", "where": [{"column": "amount", "op": "gt", "value": 100}]}, tier="full")
        self.assertNotIn("error", good)
        self.assertEqual(self.engine.dispatch("query", {"table": "orders", "measures": [{"fn": "count"}], "concepts": ["big"]})["rows"], [[1]])
        self.assertEqual(self.engine.dispatch("edit_relationship", {"table": "orders", "name": "nope", "text": "x"}, tier="full")["error"]["type"], "MetadataFormatError")
        self.engine.dispatch("edit_relationship", {"table": "orders", "name": "shipments", "text": "Parcels for the order."}, tier="full")
        self.engine.dispatch("edit_glossary", {"term": "sku", "definition": "Replaced.", "tables": ["orders"]}, tier="full")
        terms = [e.term for e in self.engine.annotated.metadata.glossary]
        self.assertEqual(terms.count("sku") + terms.count("SKU"), 1)
        self.assertEqual(self.engine.dispatch("edit_glossary", {"term": "x", "definition": "y", "tables": ["nowhere"]}, tier="full")["error"]["type"], "MetadataFormatError")


if __name__ == "__main__":
    unittest.main()
