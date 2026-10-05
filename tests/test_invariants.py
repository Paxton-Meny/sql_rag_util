"""Engine-wide safety invariants, checked end to end on a live SQLite database."""

from __future__ import annotations

import sqlite3
import unittest
from typing import Any

from sql_rag_util.config import Config, Limits, StatementEvent
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.engine import SqlRag
from sql_rag_util.search.sqlite_functions import LEVENSHTEIN_FUNCTION, SOUNDEX_FUNCTION, register_sqlite_functions
from tests.support.fixture import FIXTURE_SQL, FIXTURES, fixture_connection, writable_metadata

TOOL_CALLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("get_context", {"question": "Which open orders does Acme have?"}),
    ("query", {"table": "orders", "columns": ["id", "customer.name"], "filters": [{"column": "status", "op": "eq", "value": "open"}]}),
    ("query", {"table": "orders", "group_by": ["customer.region"], "measures": [{"fn": "measure", "column": "revenue"}], "concepts": ["active"]}),
    ("query", {"table": "orders", "filters": [{"column": "status", "op": "eq", "value": "opne"}]}),
    ("search_rows", {"table": "customers", "term": "jon smith"}),
    ("describe_table", {"table": "orders"}),
    ("list_tables", {}),
    ("edit_column", {"table": "orders", "column": "status", "text": "Lifecycle state."}),
    ("edit_concept", {"table": "orders", "name": "big", "text": "Large orders.", "where": [{"column": "amount", "op": "gt", "value": 100}]}),
    ("edit_glossary", {"term": "Backorder", "definition": "An order waiting for stock.", "tables": ["orders"]}),
)


class RecordingConnection(sqlite3.Connection):
    """A SQLite connection that counts commits and rollbacks, still detected as sqlite3."""

    __module__ = "sqlite3.recording"
    commits = 0
    rollbacks = 0

    def commit(self) -> None:
        """Count, then commit."""
        self.commits += 1
        super().commit()

    def rollback(self) -> None:
        """Count, then roll back."""
        self.rollbacks += 1
        super().rollback()


def _read_only_fixture(test: unittest.TestCase) -> RecordingConnection:
    connection = sqlite3.connect(":memory:", factory=RecordingConnection)
    test.addCleanup(connection.close)
    connection.executescript(FIXTURE_SQL)
    connection.execute("PRAGMA query_only = ON")
    return connection


class ReadOnlyTest(unittest.TestCase):
    """No tool writes to the database, commits, or leaves a transaction open."""

    def test_every_tool_only_reads(self) -> None:
        """Every statement is a SELECT, even with the toolkit writing metadata, on a connection that refuses writes."""
        connection = _read_only_fixture(self)
        register_sqlite_functions(connection)
        events: list[StatementEvent] = []
        engine = SqlRag(connection, metadata_root=writable_metadata(self), config=Config(allow_metadata_writes=True, on_statement=events.append))
        for name, arguments in TOOL_CALLS:
            with self.subTest(tool=name):
                result = engine.dispatch(name, arguments, tier="full")
                self.assertNotIn("error", result, result.get("error"))
        self.assertGreater(len(events), len(TOOL_CALLS))
        self.assertEqual([e.sql for e in events if not e.sql.startswith("SELECT ")], [])
        self.assertEqual((connection.commits, connection.rollbacks, connection.in_transaction), (0, 0, False))

    def test_matching_functions_exist_only_when_registered(self) -> None:
        """The engine never adds functions to a connection; registering them is the caller's explicit step."""
        connection = fixture_connection(self)

        def registered() -> set[str]:
            rows = connection.execute("SELECT name FROM pragma_function_list WHERE name IN (?, ?)", (SOUNDEX_FUNCTION, LEVENSHTEIN_FUNCTION))
            return {name for (name,) in rows}

        plain = SqlRag(connection)
        self.assertEqual(registered(), set())
        self.assertFalse({Capability.SOUNDEX, Capability.LEVENSHTEIN} & plain.catalog.capabilities)
        register_sqlite_functions(connection)
        self.assertEqual(registered(), {SOUNDEX_FUNCTION, LEVENSHTEIN_FUNCTION})
        self.assertLessEqual({Capability.SOUNDEX, Capability.LEVENSHTEIN}, SqlRag(connection).catalog.capabilities)


class CapsTest(unittest.TestCase):
    """Column and measure caps hold for explicit requests and default selections."""

    def setUp(self) -> None:
        limits = Limits(max_columns=2, max_measures=1)
        self.engine = SqlRag(fixture_connection(self), metadata_root=FIXTURES, config=Config(limits=limits))

    def test_column_cap(self) -> None:
        """Naming too many columns is refused; the default selection is cut with a note."""
        refused = self.engine.dispatch("query", {"table": "orders", "columns": ["id", "status", "amount"]})["error"]
        self.assertEqual((refused["type"], refused["message"]), ("LimitExceededError", "at most 2 columns per query"))
        default = self.engine.dispatch("query", {"table": "orders"})
        self.assertEqual(default["columns"], ["id", "customer_id"])
        self.assertIn("columns omitted; name the columns you need.", " ".join(default["notes"]))

    def test_measure_cap(self) -> None:
        """Asking for more aggregates than allowed is refused."""
        refused = self.engine.dispatch("query", {"table": "orders", "measures": [{"fn": "count"}, {"fn": "sum", "column": "amount"}]})["error"]
        self.assertEqual((refused["type"], refused["message"]), ("LimitExceededError", "at most 1 measures"))


class SensitiveEverywhereTest(unittest.TestCase):
    """A sensitive column is refused in every position the agent controls, directly and through joins."""

    def test_every_position(self) -> None:
        """Columns, filters, order, group_by, measures, joined paths, search columns, and agent-written concepts."""
        engine = SqlRag(fixture_connection(self), metadata_root=writable_metadata(self), config=Config(allow_metadata_writes=True))
        email = {"column": "email", "op": "eq", "value": "ops@acme.example"}
        sensitive = ("SensitiveColumnError", "column 'email' on customers is sensitive and cannot be used")
        calls: dict[str, tuple[str, dict[str, Any], tuple[str, str]]] = {
            "columns": ("query", {"table": "customers", "columns": ["email"]}, sensitive),
            "filters": ("query", {"table": "customers", "filters": [email]}, sensitive),
            "order": ("query", {"table": "customers", "order": [{"by": "email"}]}, sensitive),
            "group_by": ("query", {"table": "customers", "group_by": ["email"], "measures": [{"fn": "count"}]}, sensitive),
            "measures": ("query", {"table": "customers", "measures": [{"fn": "count_distinct", "column": "email"}]}, sensitive),
            "joined column": ("query", {"table": "orders", "columns": ["id", "customer.email"]}, sensitive),
            "joined filter": ("query", {"table": "orders", "filters": [{**email, "column": "customer.email"}]}, sensitive),
            "search columns": ("search_rows", {"table": "customers", "term": "acme", "columns": ["email"]}, ("QuerySpecError", "column 'email' is not searchable on customers")),
            "concept": ("edit_concept", {"table": "customers", "name": "acme_contact", "text": "x", "where": [email]}, ("MetadataFormatError", "tables/customers.md: concept 'acme_contact': " + sensitive[1])),
        }
        for position, (tool, arguments, expected) in calls.items():
            with self.subTest(position=position):
                error = engine.dispatch(tool, arguments, tier="full")["error"]
                self.assertEqual((error["type"], error["message"]), expected)

if __name__ == "__main__":
    unittest.main()
