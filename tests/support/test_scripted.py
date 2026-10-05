"""Tests for the scripted driver the dialect end-to-end tests stand on."""

from __future__ import annotations

import unittest

from sql_rag_util.exceptions import ExecutionError
from sql_rag_util.executor import Executor
from sql_rag_util.sql.render import PARAMSTYLES, render
from sql_rag_util.sql.statement import bind, sql
from tests.support.scripted import Rule, ScriptedConnection, ScriptError, placeholders


class PlaceholdersTest(unittest.TestCase):
    """Placeholders are read the way each paramstyle's driver reads them."""

    def test_each_style(self) -> None:
        """Quoted literals hide placeholders except under percent styles, where only %% is literal."""
        cases = [
            ("SELECT ? FROM \"a?\" WHERE b = '?' AND c = ?", "qmark", ["?", "?"]),
            ("SELECT :1 FROM t WHERE b = ':2' AND c = :2", "numeric", ["1", "2"]),
            ("SELECT :p0 FROM [x:y] WHERE c = :p1", "named", ["p0", "p1"]),
            ("SELECT a FROM t WHERE b LIKE %s ESCAPE '!' AND c = '100%%'", "format", ["s"]),
            ("SELECT a FROM t WHERE b = %(p0)s AND c = %(p1)s AND d = '5%%'", "pyformat", ["p0", "p1"]),
        ]
        for text, style, expected in cases:
            with self.subTest(style=style):
                self.assertEqual(placeholders(text, style), expected)

    def test_stray_percent_signs_and_unknown_styles(self) -> None:
        """A lone % or the other percent style's placeholder is an error, as it would be in the driver."""
        for text, style in (("WHERE a = '50%'", "format"), ("WHERE a = %(p0)s", "format"), ("WHERE a = %s", "pyformat"), ("SELECT 1", "dollar")):
            with self.subTest(text=text, style=style):
                with self.assertRaises(ScriptError):
                    placeholders(text, style)

    def test_agrees_with_the_package_renderer(self) -> None:
        """Every statement the renderer produces, with a literal %, reads back with one placeholder per bind."""
        statement = sql("SELECT a FROM t WHERE b LIKE '100%' AND c = ") + bind(1) + sql(" AND d = ") + bind("x")
        for style in PARAMSTYLES:
            with self.subTest(style=style):
                connection = ScriptedConnection([Rule("SELECT a")], paramstyle=style)
                connection.answer(*render(statement, style))
                self.assertEqual(connection.violations, [])


class ScriptedConnectionTest(unittest.TestCase):
    """Rules answer in order, every statement is recorded, and mistakes are kept as violations."""

    def test_rules_rows_and_lifecycle(self) -> None:
        """Static and computed rows come back through the executor, cursors close, and nothing commits."""
        connection = ScriptedConnection([Rule(r"FROM orders", lambda text, params: [(params[0], "open")]), Rule(r"FROM customers", [(1,), (2,)])])
        executor = Executor(connection, "qmark")
        self.assertEqual(executor.fetch(sql("SELECT id, status FROM orders WHERE id = ") + bind(10), command="query", limit=5).rows, ((10, "open"),))
        self.assertEqual(executor.fetch(sql("SELECT id FROM customers"), command="query", limit=1).rows, ((1,),))
        self.assertEqual([text for text, _ in connection.executed], ["SELECT id, status FROM orders WHERE id = ?", "SELECT id FROM customers"])
        self.assertTrue(connection.all_closed)
        self.assertEqual((connection.commits, connection.violations), (0, []))

    def test_mapping_rows_and_scripted_errors(self) -> None:
        """Rows can come back as mappings, and a rule can raise the driver's own error."""
        mapped = ScriptedConnection([Rule("SELECT", [(1, "a")])], dict_rows=True)
        cursor = mapped.cursor()
        cursor.execute("SELECT 1")
        self.assertEqual(cursor.fetchall(), [{"c0": 1, "c1": "a"}])
        failing = ScriptedConnection([Rule("SELECT", error=PermissionError("denied"))])
        with self.assertRaisesRegex(ExecutionError, "PermissionError: denied"):
            Executor(failing, "qmark").fetch(sql("SELECT 1"), command="query")
        self.assertEqual(failing.violations, [])

    def test_unscripted_statements_and_bad_binds_are_violations(self) -> None:
        """Both are recorded even when the package turns the exception into its own error."""
        connection = ScriptedConnection([Rule("SELECT")], paramstyle="format")
        executor = Executor(connection, "qmark")
        for statement in (sql("DELETE FROM t"), sql("SELECT a WHERE b = ") + bind(1)):
            with self.subTest(statement=statement):
                with self.assertRaises(ExecutionError):
                    executor.fetch(statement, command="query")
        self.assertEqual(len(connection.violations), 2)
        self.assertIn("unscripted statement 'DELETE FROM t'", connection.violations[0])
        self.assertIn("do not match", connection.violations[1])


if __name__ == "__main__":
    unittest.main()
