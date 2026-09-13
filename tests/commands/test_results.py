"""Tests for result shaping."""

from __future__ import annotations

import datetime as dt
import decimal
import unittest

from sql_rag_util.commands.results import coerce_cell, shape_rows, table_text
from sql_rag_util.config import Limits


class ShapeTest(unittest.TestCase):
    """Cells become JSON scalars, long text is cut, and text tables are tab-separated."""

    def test_coerce_cell(self) -> None:
        """Each driver type maps to a JSON scalar."""
        cases = [
            (None, None), (True, True), (3, 3), (2.5, 2.5),
            (decimal.Decimal("19.99"), 19.99), (decimal.Decimal("250.00"), 250),
            (dt.datetime(2026, 9, 13, 12, 30, 5, 123), "2026-09-13 12:30:05"), (dt.date(2026, 9, 13), "2026-09-13"),
            (dt.time(12, 30), "12:30:00"), (b"\x00\x01", "<2 bytes>"), (memoryview(b"abc"), "<3 bytes>"),
            ("plain", "plain"), (object, str(object)),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(coerce_cell(value, 200)[0], expected)
        self.assertEqual(coerce_cell("abcdef", 3), ("abc…", True))

    def test_shape_and_text(self) -> None:
        """Truncated cells are counted and text cells never contain tabs or newlines."""
        rows, cut = shape_rows([(1, "x" * 6, None), (2, "a\tb\nc", False)], Limits(max_cell_chars=5))
        self.assertEqual(cut, 1)
        self.assertEqual(rows[0], [1, "xxxxx…", None])
        self.assertEqual(table_text(["id", "name", "flag"], rows), "id\tname\tflag\n1\txxxxx…\t\n2\ta b c\tfalse")


if __name__ == "__main__":
    unittest.main()
