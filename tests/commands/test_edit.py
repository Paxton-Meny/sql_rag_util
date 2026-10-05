"""End-to-end tests of the metadata toolkit."""

from __future__ import annotations

import datetime as dt
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from sql_rag_util.exceptions import IntrospectionError
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

    def test_hidden_columns_cannot_be_edited(self) -> None:
        """An agent cannot address a hidden column, and the file keeps its flag."""
        error = self.engine.dispatch("edit_column", {"table": "orders", "column": "notes", "text": "x", "searchable": True}, tier="full")["error"]
        self.assertEqual((error["type"], error["suggestions"]), ("UnknownColumnError", []))
        self.assertIn("- notes [hidden]: Staff notes.", (self.root / "tables" / "orders.md").read_text())

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

    def _files(self) -> dict[str, str]:
        return {p.relative_to(self.root).as_posix(): p.read_text() for p in sorted(self.root.rglob("*.md"))}

    def test_text_that_would_add_structure_is_refused(self) -> None:
        """Line breaks, direction controls, commas in lists, and bad names change nothing on disk."""
        cases = [
            ("edit_table", {"table": "orders", "purpose": "p\nsynonyms: injected"}),
            ("edit_table", {"table": "orders", "description": "x\n## Columns\n\n- email: unflagged"}),
            ("edit_table", {"table": "orders", "synonyms": ["order, purchase"]}),
            ("edit_column", {"table": "customers", "column": "region", "text": "t\n- email: unflagged"}),
            ("edit_column", {"table": "customers", "column": "region", "text": "t\u2028- email: unflagged"}),
            ("edit_column", {"table": "customers", "column": "region", "text": "t", "values": ["north,south"]}),
            ("edit_relationship", {"table": "orders", "name": "shipments", "text": "x\n- notes: y"}),
            ("edit_concept", {"table": "orders", "name": "Big One", "text": "x", "where": [{"column": "amount", "op": "gt", "value": 1}]}),
            ("edit_concept", {"table": "orders", "name": "big", "text": "x\u202ey", "where": [{"column": "amount", "op": "gt", "value": 1}]}),
            ("edit_glossary", {"term": "a\nb", "definition": "x"}),
            ("edit_glossary", {"term": "a]", "definition": "x"}),
            ("edit_glossary", {"term": "sku", "definition": "x", "synonyms": ["a,b"]}),
        ]
        before = self._files()
        for tool, arguments in cases:
            with self.subTest(tool=tool, arguments=arguments):
                result = self.engine.dispatch(tool, arguments, tier="full")
                self.assertIn(result.get("error", {}).get("type"), ("QuerySpecError", "MetadataFormatError"))
                self.assertEqual(self._files(), before)
        conn = build_fixture()
        self.addCleanup(conn.close)
        SqlRag(conn, metadata_root=self.root)

    def test_flags_survive_a_two_step_injection(self) -> None:
        """Text cannot plant a second, unflagged entry that a later edit would keep instead of the flagged one."""
        self.engine.dispatch("edit_column", {"table": "customers", "column": "region", "text": "t\n- email: unflagged"}, tier="full")
        result = self.engine.dispatch("edit_column", {"table": "customers", "column": "email", "text": "Contact address."}, tier="full")
        self.assertNotIn("error", result)
        text = (self.root / "tables" / "customers.md").read_text()
        self.assertEqual(text.count("- email"), 1)
        self.assertIn("- email [sensitive]: Contact address.", text)

    def test_disk_changes_since_load_refuse_the_edit(self) -> None:
        """A developer's edit on disk is never overwritten; the engine reloads and a retry applies on top."""
        path = self.root / "tables" / "orders.md"
        developer = path.read_text().replace("- notes [hidden]: Staff notes.", "- notes [hidden]: Staff notes.\n- billing_customer_id [sensitive]: Who pays.")
        path.write_text(developer)
        result = self.engine.dispatch("edit_column", {"table": "orders", "column": "status", "text": "State."}, tier="full")
        self.assertEqual(result["error"]["type"], "MetadataConflictError")
        self.assertEqual(path.read_text(), developer)
        self.assertTrue(self.engine.annotated.policy.is_sensitive(next(t.ref for t in self.engine.catalog.tables if t.ref.name == "orders"), "billing_customer_id"))
        self.assertNotIn("error", self.engine.dispatch("edit_column", {"table": "orders", "column": "status", "text": "State."}, tier="full"))
        self.assertIn("- billing_customer_id [sensitive]: Who pays.", path.read_text())

    def test_failed_refresh_restores_the_previous_file(self) -> None:
        """When the engine cannot reload after a write, the file goes back to what it was, or away if it was new."""
        before = self._files()
        with mock.patch.object(self.engine, "refresh", side_effect=IntrospectionError("database went away")):
            changed = self.engine.dispatch("edit_column", {"table": "orders", "column": "status", "text": "State."}, tier="full")
            created = self.engine.dispatch("edit_table", {"table": "shipments", "purpose": "One row per parcel."}, tier="full")
        self.assertEqual((changed["error"]["type"], created["error"]["type"]), ("IntrospectionError", "IntrospectionError"))
        self.assertEqual(self._files(), before)


if __name__ == "__main__":
    unittest.main()
