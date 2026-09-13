"""Regression caps on context cost, measured on the fixture."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import unittest

from sql_rag_util.engine import SqlRag
from tests.support.fixture import build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "metadata"
CAPS = {
    ("describe_table", "json"): 1800,
    ("describe_table", "compact"): 900,
    ("get_context", "json"): 4200,
    ("get_context", "compact"): 1400,
    ("list_tables", "compact"): 300,
    ("query", "compact"): 200,
}


class CostTest(unittest.TestCase):
    """Outputs stay under the caps recorded in docs/context-cost.md."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name) / "meta"
        shutil.copytree(FIXTURES, root)
        conn = build_fixture()
        self.addCleanup(conn.close)
        self.engine = SqlRag(conn, metadata_root=root)

    def _size(self, name: str, arguments: dict, fmt: str) -> int:  # type: ignore[type-arg]
        if fmt == "compact":
            return len(self.engine.dispatch_text(name, arguments).encode())
        return len(json.dumps(self.engine.dispatch(name, arguments), separators=(",", ":")).encode())

    def test_caps(self) -> None:
        """Each output is under its cap."""
        calls = {
            "describe_table": {"table": "orders"},
            "get_context": {"question": "Which open orders does Acme Corp have?"},
            "list_tables": {},
            "query": {"table": "orders", "group_by": ["status"], "measures": [{"fn": "count"}]},
        }
        for (name, fmt), cap in CAPS.items():
            with self.subTest(tool=name, format=fmt):
                self.assertLessEqual(self._size(name, calls[name], fmt), cap)

    def test_tool_definitions_budget(self) -> None:
        """The standard tier's definitions fit a modest budget."""
        total = sum(len(json.dumps({"name": s.name, "description": s.description, "input_schema": s.input_schema()}).encode()) for s in self.engine.tool_specs())
        self.assertLessEqual(total, 9000)
        self.assertLessEqual(len(self.engine.instructions().encode()), 1800)


if __name__ == "__main__":
    unittest.main()
