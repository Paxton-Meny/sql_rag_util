"""Tests for the executor."""

from __future__ import annotations

import sqlite3
import unittest

from sql_rag_util.config import StatementEvent
from sql_rag_util.exceptions import ExecutionError
from sql_rag_util.executor import Executor
from sql_rag_util.sql.statement import bind, sql
from tests.support.fakes import FakeConnection, FakeCursor


class ExecutorTest(unittest.TestCase):
    """Statements render, execute once, fetch limit plus one, and close the cursor."""

    def test_fetch_with_limit_reports_truncation_honestly(self) -> None:
        """Three rows behind a limit of two come back as two rows and truncated."""
        cursor = FakeCursor(rows=[(1,), (2,), (3,)])
        events: list[StatementEvent] = []
        executor = Executor(FakeConnection([cursor]), "format", on_statement=events.append)
        fetched = executor.fetch(sql("SELECT a FROM t WHERE b = ") + bind(5), command="query", limit=2)
        self.assertEqual(fetched.rows, ((1,), (2,)))
        self.assertTrue(fetched.truncated)
        self.assertEqual(cursor.executed, [("SELECT a FROM t WHERE b = %s", (5,))])
        self.assertTrue(cursor.closed)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].command, events[0].parameter_count, events[0].row_count), ("query", 1, 2))
        self.assertNotIn("5", events[0].sql)

    def test_fetch_exact_limit_is_not_truncated(self) -> None:
        """Exactly limit rows is not truncation."""
        executor = Executor(FakeConnection([FakeCursor(rows=[(1,), (2,)])]), "qmark")
        fetched = executor.fetch(sql("SELECT 1"), command="query", limit=2)
        self.assertEqual((fetched.rows, fetched.truncated), (((1,), (2,)), False))

    def test_fetch_all_for_introspection(self) -> None:
        """No limit fetches every row and never reports truncation."""
        executor = Executor(FakeConnection([FakeCursor(rows=[(1,), (2,), (3,)])]), "qmark")
        fetched = executor.fetch(sql("SELECT 1"), command="introspect")
        self.assertEqual((len(fetched.rows), fetched.truncated), (3, False))

    def test_driver_errors_are_wrapped_and_cursor_closed(self) -> None:
        """A driver exception becomes ExecutionError naming the command; nothing is committed."""
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        executor = Executor(conn, "qmark")
        with self.assertRaises(ExecutionError) as ctx:
            executor.fetch(sql("SELECT * FROM missing"), command="query", limit=1)
        self.assertIn("query", str(ctx.exception))
        self.assertIn("missing", str(ctx.exception))

    def test_cursor_failures_never_escape_unwrapped(self) -> None:
        """Opening a cursor, executing, and closing all fail as ExecutionError; a close failure never masks the cause."""

        class NoCursor(FakeConnection):
            def cursor(self) -> FakeCursor:
                raise ConnectionError("server closed the connection")

        class Broken(FakeCursor):
            def execute(self, sql: str, params: object) -> None:
                raise ValueError("syntax error")

            def close(self) -> None:
                raise OSError("socket gone")

        class CloseFails(FakeCursor):
            def close(self) -> None:
                raise OSError("socket gone")

        cases = [
            (NoCursor(), "ConnectionError: server closed the connection"),
            (FakeConnection([Broken()]), "ValueError: syntax error"),
            (FakeConnection([CloseFails(rows=[(1,)])]), "OSError: socket gone"),
        ]
        for connection, cause in cases:
            with self.subTest(cause=cause):
                with self.assertRaisesRegex(ExecutionError, f"^query: {cause}$"):
                    Executor(connection, "qmark").fetch(sql("SELECT 1"), command="query", limit=1)

    def test_mapping_rows_become_value_tuples(self) -> None:
        """Drivers configured to return dictionaries yield the same tuples as plain cursors."""
        cursor = FakeCursor(rows=[{"id": 1, "name": "Acme"}, {"id": 2, "name": "Zeta"}])
        fetched = Executor(FakeConnection([cursor]), "pyformat").fetch(sql("SELECT id, name FROM t"), command="query", limit=5)
        self.assertEqual(fetched.rows, ((1, "Acme"), (2, "Zeta")))

    def test_live_sqlite_and_no_commit(self) -> None:
        """Rows come back as tuples from a real connection and the fake never sees a commit."""
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])
        fetched = Executor(conn, "qmark").fetch(sql("SELECT a FROM t ORDER BY a"), command="query", limit=5)
        self.assertEqual(fetched.rows, ((1,), (2,)))
        fake = FakeConnection([FakeCursor()])
        Executor(fake, "qmark").fetch(sql("SELECT 1"), command="query", limit=1)
        self.assertEqual(fake.commits, 0)


if __name__ == "__main__":
    unittest.main()
