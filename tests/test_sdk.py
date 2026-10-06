"""Tests for the SDK surface documented in docs/sdk.md."""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import unittest
from dataclasses import replace

from sql_rag_util.commands.dispatch import Dispatcher
from sql_rag_util.commands.spec import CommandResult
from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from sql_rag_util.exceptions import MetadataFormatError
from sql_rag_util.metadata.model import ColumnMeta
from sql_rag_util.schema.model import TableRef
from tests.support.fixture import fixture_connection, writable_metadata

DOCUMENT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "sdk.md"
CUSTOMERS = TableRef(None, "customers")


class SdkTest(unittest.TestCase):
    """Every member the SDK page names behaves as it says, and its recipe runs."""

    def setUp(self) -> None:
        self.root = writable_metadata(self)
        self.engine = SqlRag(fixture_connection(self), metadata_root=self.root, config=Config(allow_metadata_writes=True))

    def test_recipe_runs_as_written(self) -> None:
        """The custom tool example prints the open orders of the customer it names."""
        code = re.findall(r"```python\n(.*?)```", DOCUMENT.read_text(encoding="utf-8"), re.S)[-1]
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            exec(compile(code, str(DOCUMENT), "exec"), {"engine": self.engine})
        self.assertEqual(printed.getvalue(), "[[10, 19.99]]\n")

    def test_running_members(self) -> None:
        """run returns the raw result, dispatcher and tool_specs follow the tier, and instructions name the tools."""
        self.assertIsInstance(self.engine.run("list_tables", {}), CommandResult)
        self.assertIsInstance(self.engine.dispatcher(tier="minimal"), Dispatcher)
        self.assertEqual([s.name for s in self.engine.tool_specs(tier="minimal")], ["get_context", "query"])
        self.assertIn("edit_column", [s.name for s in self.engine.tool_specs(tier="full")])
        self.assertIn("get_context", self.engine.instructions())

    def test_catalog_views(self) -> None:
        """The agent catalog drops hidden columns; annotated.full keeps them; the policy says which."""
        full_catalog = self.engine.annotated.full
        assert full_catalog is not None
        agent, full = self.engine.catalog.require(CUSTOMERS), full_catalog.require(CUSTOMERS)
        self.assertNotIn("password_hash", [c.name for c in agent.columns])
        self.assertIn("password_hash", [c.name for c in full.columns])
        self.assertTrue(self.engine.annotated.policy.is_hidden(CUSTOMERS, "password_hash"))

    def test_building_blocks(self) -> None:
        """The retriever builds lazily, metadata validates against the live catalog, and refresh picks up file edits."""
        self.assertFalse(self.engine.retriever_ready)
        self.engine.dispatch("get_context", {"question": "orders"})
        self.assertTrue(self.engine.retriever_ready)
        metadata = self.engine.annotated.metadata
        orders = metadata.table("orders")
        assert orders is not None
        broken = replace(metadata, tables=tuple(replace(t, columns=(*t.columns, ColumnMeta("no_such_column", "x"))) if t is orders else t for t in metadata.tables))
        with self.assertRaisesRegex(MetadataFormatError, "no_such_column"):
            self.engine.validate_metadata(broken)
        self.engine.validate_metadata(metadata)
        assert self.engine.store is not None
        path = self.engine.store.table_path("orders")
        path.write_text(path.read_text().replace("purpose: One row per customer order.", "purpose: One order."))
        version = self.engine.schema_version
        self.engine.refresh()
        self.assertEqual(self.engine.annotated.metadata.table("orders").purpose, "One order.")
        self.assertNotEqual(self.engine.schema_version, version)
        self.assertFalse(self.engine.retriever_ready)


if __name__ == "__main__":
    unittest.main()
