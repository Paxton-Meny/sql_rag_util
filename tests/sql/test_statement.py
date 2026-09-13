"""Tests for the statement model."""

from __future__ import annotations

import unittest

from sql_rag_util.exceptions import StatementError
from sql_rag_util.sql.statement import Bind, Statement, bind, join, sql


class StatementTest(unittest.TestCase):
    """Statements concatenate, join, and expose their binds."""

    def test_add_and_join(self) -> None:
        """Concatenation preserves order; join inserts separators between items."""
        combined = sql("SELECT ") + bind(1) + sql(" + ") + bind(2)
        self.assertEqual(combined.text_preview, "SELECT ? + ?")
        self.assertEqual([b.value for b in combined.binds], [1, 2])
        joined = join(", ", (bind("a"), bind("b"), bind("c")))
        self.assertEqual(joined.text_preview, "?, ?, ?")
        self.assertEqual(join(", ", ()).parts, ())

    def test_empty_detection(self) -> None:
        """A statement with no parts or only empty text is empty; a bind is not."""
        self.assertTrue(Statement().is_empty)
        self.assertTrue(sql("").is_empty)
        self.assertFalse(bind(None).is_empty)

    def test_bind_refuses_collections(self) -> None:
        """Lists, tuples, sets, and dicts must be expanded by the builder."""
        for value in ([1], (1,), {1}, {"a": 1}):
            with self.subTest(value=value):
                with self.assertRaises(StatementError):
                    Bind(value)


if __name__ == "__main__":
    unittest.main()
