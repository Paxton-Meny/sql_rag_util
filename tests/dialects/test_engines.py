"""End-to-end engines on PostgreSQL, MySQL, and SQL Server drivers, without a server.

Each driver is a scripted connection that answers introspection with the
fixture schema in that database's row shapes and type names, so a full
:class:`SqlRag` is built and every tool runs. The connection checks that every
statement's placeholders match its parameters in the driver's paramstyle.
"""

from __future__ import annotations

import re
import unittest
from typing import Any

from sql_rag_util.config import Config
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.engine import SqlRag
from sql_rag_util.schema.model import ColumnKind
from tests.support.fixture import writable_metadata
from tests.support.introspection import introspection_rules
from tests.support.scripted import Rule, ScriptedConnection, scripted_driver

DRIVERS = (
    ("postgres", "psycopg", "pyformat"),
    ("postgres", "pg8000", "format"),
    ("mysql", "pymysql", "pyformat"),
    ("mysql", "MySQLdb", "format"),
    ("mssql", "pymssql", "pyformat"),
    ("mssql", "pyodbc", "qmark"),
)
EXTENSIONS = ("pg_trgm", "fuzzystrmatch")
CAPABILITIES = {
    "postgres": {Capability.CASE_INSENSITIVE_LIKE, Capability.ROW_ESTIMATE, Capability.TRIGRAM, Capability.LEVENSHTEIN, Capability.SOUNDEX, Capability.DIFFERENCE},
    "mysql": {Capability.CASE_INSENSITIVE_LIKE, Capability.ROW_ESTIMATE, Capability.SOUNDEX},
    "mssql": {Capability.SOUNDEX, Capability.DIFFERENCE, Capability.FULLTEXT, Capability.ROW_ESTIMATE},
}
INTROSPECTION_STATEMENTS = {"postgres": 13, "mysql": 12, "mssql": 12}
QUERY = {"table": "orders", "columns": ["id", "customer.name"], "filters": [{"column": "status", "op": "eq", "value": "open"}]}
GOLDEN_QUERY = {
    "postgres": 'SELECT "t0"."id" AS "id", "t1"."name" AS "customer.name" FROM "orders" AS "t0" LEFT JOIN "customers" AS "t1" ON "t0"."customer_id" = "t1"."id" WHERE ("t0"."status" = ?) ORDER BY "t0"."id" LIMIT ?',
    "mysql": "SELECT `t0`.`id` AS `id`, `t1`.`name` AS `customer.name` FROM `orders` AS `t0` LEFT JOIN `customers` AS `t1` ON `t0`.`customer_id` = `t1`.`id` WHERE (`t0`.`status` = ?) ORDER BY `t0`.`id` LIMIT ?",
    "mssql": "SELECT TOP (?) [t0].[id] AS [id], [t1].[name] AS [customer.name] FROM [orders] AS [t0] LEFT JOIN [customers] AS [t1] ON [t0].[customer_id] = [t1].[id] WHERE ([t0].[status] = ?) ORDER BY [t0].[id]",
}
GOLDEN_SEARCH_WORD = {
    "postgres": "(\"t0\".\"name\" ILIKE ? ESCAPE '!' OR soundex(\"t0\".\"name\") = soundex(?) OR levenshtein_less_equal(\"t0\".\"name\", ?, ?) <= ? OR similarity(\"t0\".\"name\", ?) >= ?)",
    "mysql": "(`t0`.`name` LIKE ? ESCAPE '!' OR SOUNDEX(`t0`.`name`) = SOUNDEX(?))",
    "mssql": "([t0].[name] LIKE ? ESCAPE '!' OR SOUNDEX([t0].[name]) = SOUNDEX(?))",
}
TOOL_CALLS = (
    ("query", QUERY),
    ("query", {"table": "orders", "group_by": ["customer.region"], "measures": [{"fn": "measure", "column": "revenue"}], "concepts": ["active"]}),
    ("query", {"table": "customers", "filters": [{"column": "name", "op": "contains", "value": "100%"}]}),
    ("search_rows", {"table": "customers", "term": "50% acme"}),
    ("get_context", {"question": "Which open orders does Acme have?"}),
    ("describe_table", {"table": "orders"}),
    ("list_tables", {}),
    ("edit_column", {"table": "orders", "column": "status", "text": "Lifecycle state."}),
)
_PLACEHOLDER = re.compile(r"%\(p\d+\)s|%s|:\d+|:p\d+|\?")


def _normalized(text: str) -> str:
    return _PLACEHOLDER.sub("?", text)


def _values(parameters: Any) -> list[object]:
    return list(parameters.values()) if isinstance(parameters, dict) else list(parameters)


class DialectEngineTest(unittest.TestCase):
    """Every driver builds the fixture catalog, runs every tool read-only, and binds every value."""

    def _engine(self, dialect: str, driver: str, paramstyle: str, *, rows: list[Rule] | None = None, dict_rows: bool = False) -> tuple[SqlRag, ScriptedConnection]:
        connection_type = scripted_driver(self, driver, paramstyle)
        rules = introspection_rules(dialect, paramstyle, extensions=EXTENSIONS) + (rows or []) + [Rule(r"^SELECT ", [])]
        connection = connection_type(rules, paramstyle=paramstyle, dict_rows=dict_rows)
        explicit = dialect if driver == "pyodbc" else None
        engine = SqlRag(connection, dialect=explicit, metadata_root=writable_metadata(self), config=Config(allow_metadata_writes=True))
        return engine, connection

    def test_catalog_is_built_from_driver_answers(self) -> None:
        """Tables, kinds, keys, renamed relationships, and probed capabilities match the fixture."""
        for dialect, driver, paramstyle in DRIVERS:
            with self.subTest(driver=driver):
                engine, connection = self._engine(dialect, driver, paramstyle)
                self.assertEqual((engine.dialect.name, engine.executor.paramstyle), (dialect, paramstyle))
                self.assertEqual(len(connection.executed), INTROSPECTION_STATEMENTS[dialect])
                self.assertEqual([t.ref.qualified for t in engine.catalog.tables], ["customers", "employees", "orders", "shipment_events", "shipments"])
                orders = next(t for t in engine.catalog.tables if t.ref.name == "orders")
                self.assertEqual({c.name: c.kind for c in orders.columns}["amount"], ColumnKind.DECIMAL)
                self.assertEqual(orders.primary_key, ("id",))
                self.assertIn("customer", [r.name for r in engine.catalog.relationships_of(orders.ref)])
                self.assertEqual(set(engine.catalog.capabilities), CAPABILITIES[dialect])

    def test_every_tool_runs_read_only_with_matching_binds(self) -> None:
        """No tool errors, every statement is a SELECT with one parameter per placeholder, and nothing commits."""
        for dialect, driver, paramstyle in DRIVERS:
            with self.subTest(driver=driver):
                engine, connection = self._engine(dialect, driver, paramstyle)
                for name, arguments in TOOL_CALLS:
                    result = engine.dispatch(name, arguments, tier="full")
                    self.assertNotIn("error", result, f"{name}: {result.get('error')}")
                self.assertEqual(connection.violations, [])
                self.assertEqual([t for t, _ in connection.executed if not t.startswith("SELECT ")], [])
                self.assertEqual(connection.commits, 0)
                self.assertTrue(connection.all_closed)

    def test_golden_statements_and_escaped_values(self) -> None:
        """Queries and searches take each dialect's exact shape, and a literal % in a term is escaped."""
        for dialect, driver, paramstyle in DRIVERS:
            with self.subTest(driver=driver):
                engine, connection = self._engine(dialect, driver, paramstyle)
                start = len(connection.executed)
                engine.dispatch("query", QUERY)
                engine.dispatch("search_rows", {"table": "customers", "term": "50% acme"})
                (query_text, _), (search_text, search_parameters) = connection.executed[start:]
                self.assertEqual(_normalized(query_text), GOLDEN_QUERY[dialect])
                self.assertIn(f"({GOLDEN_SEARCH_WORD[dialect]} AND {GOLDEN_SEARCH_WORD[dialect]})", _normalized(search_text))
                self.assertIn("%50!%%", _values(search_parameters))

    def test_rows_and_driver_errors_reach_the_agent(self) -> None:
        """Rows, including mapping rows, come back in column order; a driver error becomes an error envelope."""

        class ProgrammingError(Exception):
            """Stands in for a driver's own exception class."""

        for dialect, driver, paramstyle in DRIVERS:
            for dict_rows in (False, True):
                with self.subTest(driver=driver, dict_rows=dict_rows):
                    answers = [Rule(r"FROM .orders. AS", [(10, "Acme Corp")]), Rule(r"FROM .customers. AS", error=ProgrammingError("permission denied for table customers"))]
                    engine, connection = self._engine(dialect, driver, paramstyle, rows=answers, dict_rows=dict_rows)
                    self.assertEqual(engine.dispatch("query", QUERY)["rows"], [[10, "Acme Corp"]])
                    error = engine.dispatch("query", {"table": "customers", "columns": ["name"]})["error"]
                    self.assertEqual(error["type"], "ExecutionError")
                    self.assertIn("ProgrammingError: permission denied for table customers", error["message"])
                    self.assertTrue(connection.all_closed)


if __name__ == "__main__":
    unittest.main()
