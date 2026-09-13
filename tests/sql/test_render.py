"""Tests for rendering statements to each paramstyle."""

from __future__ import annotations

import unittest

from sql_rag_util.exceptions import StatementError
from sql_rag_util.sql.render import PARAMSTYLES, render
from sql_rag_util.sql.statement import Statement, bind, sql

STATEMENT = sql('SELECT "a?b" FROM t WHERE x = ') + bind(1) + sql(" AND y LIKE ") + bind("50%")


class RenderTest(unittest.TestCase):
    """One renderer covers every paramstyle without touching identifiers."""

    def test_each_paramstyle(self) -> None:
        """Placeholders and parameter containers match the style; text is otherwise verbatim."""
        expected = {
            "qmark": ('SELECT "a?b" FROM t WHERE x = ? AND y LIKE ?', (1, "50%")),
            "format": ('SELECT "a?b" FROM t WHERE x = %s AND y LIKE %s', (1, "50%")),
            "pyformat": ('SELECT "a?b" FROM t WHERE x = %(p0)s AND y LIKE %(p1)s', {"p0": 1, "p1": "50%"}),
            "named": ('SELECT "a?b" FROM t WHERE x = :p0 AND y LIKE :p1', {"p0": 1, "p1": "50%"}),
            "numeric": ('SELECT "a?b" FROM t WHERE x = :1 AND y LIKE :2', (1, "50%")),
        }
        self.assertEqual(set(expected), PARAMSTYLES)
        for style, want in expected.items():
            with self.subTest(style=style):
                self.assertEqual(render(STATEMENT, style), want)

    def test_percent_in_text_is_doubled_only_for_format_styles(self) -> None:
        """A literal percent in a fragment survives the driver's own formatting."""
        statement = sql('SELECT "100%" FROM t WHERE a = ') + bind(1)
        self.assertEqual(render(statement, "format")[0], 'SELECT "100%%" FROM t WHERE a = %s')
        self.assertEqual(render(statement, "pyformat")[0], 'SELECT "100%%" FROM t WHERE a = %(p0)s')
        self.assertEqual(render(statement, "qmark")[0], 'SELECT "100%" FROM t WHERE a = ?')
        self.assertEqual(render(statement, "named")[0], 'SELECT "100%" FROM t WHERE a = :p0')

    def test_bound_values_are_never_escaped(self) -> None:
        """A percent inside a bound value is passed through untouched."""
        self.assertEqual(render(STATEMENT, "format")[1], (1, "50%"))

    def test_rejections(self) -> None:
        """Unknown paramstyles and empty statements are refused."""
        with self.assertRaises(StatementError):
            render(STATEMENT, "dollar")
        with self.assertRaises(StatementError):
            render(Statement(), "qmark")


if __name__ == "__main__":
    unittest.main()
