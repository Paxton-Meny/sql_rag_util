"""Tests for the SDK surface documented in docs/sdk.md."""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
import shutil
import unittest
from dataclasses import dataclass, field, replace

from sql_rag_util.adapters import anthropic, mcp, openai
from sql_rag_util.commands.dispatch import Dispatcher
from sql_rag_util.commands.spec import CommandResult, Tier, ToolSpec
from sql_rag_util.config import Config
from sql_rag_util.engine import SqlRag
from sql_rag_util.exceptions import MetadataFormatError, ToolSpecError
from sql_rag_util.mcp.server import handle_message
from sql_rag_util.metadata.model import ColumnMeta
from sql_rag_util.schema.model import TableRef
from tests.support.fixture import fixture_connection, writable_metadata
from tests.support.scripted import ScriptedConnection

DOCUMENT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "sdk.md"
CUSTOMERS = TableRef(None, "customers")


@dataclass(frozen=True, slots=True)
class EchoArgs:
    """Arguments of the test tools."""

    word: str = field(default="", metadata={"description": "A word to echo."})


def _echo(engine: SqlRag, args: EchoArgs) -> CommandResult:
    return CommandResult({"echo": args.word}, args.word)


def _tool(name: str, tier: Tier, *, mutating: bool = False) -> ToolSpec:
    return ToolSpec(name, name.title(), f"Echo a word ({name}).", EchoArgs, _echo, tier=tier, mutating=mutating, examples=({"word": "hi"},))


class SdkTest(unittest.TestCase):
    """Every member the SDK page names behaves as it says, and its recipe runs."""

    def setUp(self) -> None:
        self.root = writable_metadata(self)
        self.engine = SqlRag(fixture_connection(self), metadata_root=self.root, config=Config(allow_metadata_writes=True))

    def test_recipe_runs_as_written(self) -> None:
        """The custom tool example, run beside sqlrag_metadata/, prints the open orders of the customer it names."""
        code = re.findall(r"```python\n(.*?)```", DOCUMENT.read_text(encoding="utf-8"), re.S)[-1]
        shutil.copytree(self.root, self.root.parent / "work" / "sqlrag_metadata")
        previous = pathlib.Path.cwd()
        os.chdir(self.root.parent / "work")
        self.addCleanup(os.chdir, previous)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            exec(compile(code, str(DOCUMENT), "exec"), {"connection": fixture_connection(self)})
        self.assertEqual(printed.getvalue(), "[[10, 19.99]]\n")

    def test_custom_tools_are_served_everywhere(self) -> None:
        """A custom tool is listed by every adapter and the MCP server, dispatched, and gated by tier and writes."""
        engine = SqlRag(fixture_connection(self), tools=(_tool("ping", "standard"), _tool("record", "full", mutating=True)))
        self.assertIn("ping", [s.name for s in engine.tool_specs()])
        for adapter in (anthropic, openai, mcp):
            with self.subTest(adapter=adapter.__name__):
                definitions = adapter.tool_definitions(engine)
                self.assertIn("ping", [d.get("name") or d["function"]["name"] for d in definitions])
        self.assertEqual(engine.dispatch("ping", {"word": "hi"})["echo"], "hi")
        listed = handle_message(engine, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertIn("ping", [t["name"] for t in listed["result"]["tools"]])
        self.assertNotIn("ping", [s.name for s in engine.tool_specs(tier="minimal")])
        self.assertNotIn("record", [s.name for s in engine.tool_specs(tier="full")])
        writable = SqlRag(fixture_connection(self), config=Config(allow_metadata_writes=True), tools=(_tool("record", "full", mutating=True),))
        self.assertIn("record", [s.name for s in writable.tool_specs(tier="full")])

    def test_taken_names_are_refused_before_reading_the_database(self) -> None:
        """A custom tool named like a built-in, or twice, fails construction without a statement being run."""
        connection = ScriptedConnection([])
        for tools in ((_tool("query", "standard"),), (_tool("ping", "standard"), _tool("ping", "full"))):
            with self.subTest(tools=[t.name for t in tools]):
                with self.assertRaisesRegex(ToolSpecError, "is already registered"):
                    SqlRag(connection, dialect="sqlite", tools=tools)
        self.assertEqual(connection.executed, [])

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
