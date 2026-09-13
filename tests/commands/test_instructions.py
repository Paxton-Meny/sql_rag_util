"""Tests for the instructions block."""

from __future__ import annotations

import pathlib
import unittest

from sql_rag_util.engine import SqlRag
from tests.support.fixture import build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


class InstructionsTest(unittest.TestCase):
    """The block names the workflow, the dialect, the version, and the project."""

    def test_instructions(self) -> None:
        """Every tool in the workflow is named and the block stays short."""
        conn = build_fixture()
        self.addCleanup(conn.close)
        engine = SqlRag(conn, metadata_root=FIXTURES)
        text = engine.instructions()
        for name in ("get_context", "describe_table", "query", "search_rows", "list_tables"):
            with self.subTest(name=name):
                self.assertIn(name, text)
        self.assertIn("dialect sqlite; 5 tables", text)
        self.assertIn(engine.schema_version, text)
        self.assertIn("About the data: Order management", text)
        self.assertLess(len(text), 1800)
        bare = SqlRag(conn)
        self.assertNotIn("About the data", bare.instructions())


if __name__ == "__main__":
    unittest.main()
