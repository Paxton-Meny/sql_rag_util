"""Tests for result shaping."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import unittest

from sql_rag_util.commands.results import coerce_cell, shape_rows, table_text
from sql_rag_util.config import Limits
from sql_rag_util.engine import SqlRag
from tests.support.fixture import fixture_connection


def _strict(text: str) -> object:
    def refuse(name: str) -> object:
        raise ValueError(name)

    return json.loads(text, parse_constant=refuse)


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

    def test_values_json_cannot_represent(self) -> None:
        """NaN, infinities, signaling NaN, and huge decimals become strict JSON and never raise."""
        cases = [
            (float("nan"), "NaN"), (float("inf"), "Infinity"), (float("-inf"), "-Infinity"),
            (decimal.Decimal("NaN"), "NaN"), (decimal.Decimal("sNaN"), "NaN"),
            (decimal.Decimal("Infinity"), "Infinity"), (decimal.Decimal("-Infinity"), "-Infinity"),
            (decimal.Decimal("1E+2000"), "1E+2000"), (decimal.Decimal("1.5E+400"), int("15" + "0" * 399)),
            (decimal.Decimal("123456789012345678901234567890"), 123456789012345678901234567890),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                cell = coerce_cell(value, 200)[0]
                self.assertEqual(cell, expected)
                self.assertEqual(_strict(json.dumps(cell, allow_nan=False)), expected)

    def test_infinite_cells_reach_agents_as_strict_json(self) -> None:
        """A REAL column holding infinities comes back through dispatch as valid JSON."""
        conn = fixture_connection(self)
        conn.executescript("CREATE TABLE readings (id INTEGER PRIMARY KEY, value REAL); INSERT INTO readings VALUES (1, 1e999), (2, -1e999), (3, 0.5);")
        engine = SqlRag(conn)
        envelope = _strict(engine.dispatcher().call_json("query", {"table": "readings"}))
        self.assertEqual(envelope["rows"], [[1, "Infinity"], [2, "-Infinity"], [3, 0.5]])

    def test_shape_and_text(self) -> None:
        """Truncated cells are counted and text cells never contain tabs or newlines."""
        rows, cut = shape_rows([(1, "x" * 6, None), (2, "a\tb\nc", False)], Limits(max_cell_chars=5))
        self.assertEqual(cut, 1)
        self.assertEqual(rows[0], [1, "xxxxx…", None])
        self.assertEqual(table_text(["id", "name", "flag"], rows), "id\tname\tflag\n1\txxxxx…\t\n2\ta b c\tfalse")


if __name__ == "__main__":
    unittest.main()
