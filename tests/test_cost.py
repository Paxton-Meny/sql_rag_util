"""Regression caps on context cost, measured on the fixture."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import unittest

from benchmarks import run as benchmark
from sql_rag_util.engine import SqlRag
from tests.support.fixture import fixture_connection, writable_metadata

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
        self.engine = SqlRag(fixture_connection(self), metadata_root=writable_metadata(self))

    def _definitions(self, tier: str) -> int:
        return sum(len(json.dumps({"name": s.name, "description": s.description, "input_schema": s.input_schema()}).encode()) for s in self.engine.tool_specs(tier=tier))

    def _size(self, name: str, arguments: dict[str, object], fmt: str) -> int:
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
        self.assertLessEqual(self._definitions("standard"), 9000)
        self.assertLessEqual(len(self.engine.instructions().encode()), 1800)

    def test_documented_numbers_are_current(self) -> None:
        """The cost document shows exactly what the benchmark prints and the tier sizes it quotes."""
        document = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "context-cost.md").read_text(encoding="utf-8")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            benchmark.main()
        self.assertIn(printed.getvalue(), document)
        self.assertIn(f"to {self._definitions('minimal')} bytes against {self._definitions('standard')}", document)


if __name__ == "__main__":
    unittest.main()
