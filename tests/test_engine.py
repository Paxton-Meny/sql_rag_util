"""Tests for the SqlRag facade."""

from __future__ import annotations

import pathlib
import unittest

from sql_rag_util.config import Config, Limits
from sql_rag_util.engine import SqlRag
from sql_rag_util.exceptions import ConfigurationError, DialectDetectionError
from sql_rag_util.query.spec import Filter, FilterOp
from sql_rag_util.schema.model import TableRef
from tests.support.fakes import fake_driver
from tests.support.fixture import build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "metadata"


class EngineTest(unittest.TestCase):
    """Construction detects the dialect, introspects, annotates, and exposes tools."""

    def setUp(self) -> None:
        self.conn = build_fixture()
        self.addCleanup(self.conn.close)

    def test_construct_with_metadata(self) -> None:
        """The fixture database and metadata load; the version is stable across refresh."""
        engine = SqlRag(self.conn, metadata_root=FIXTURES)
        self.assertEqual(engine.dialect.name, "sqlite")
        self.assertEqual(engine.executor.paramstyle, "qmark")
        self.assertTrue(engine.annotated.policy.is_sensitive(TableRef(None, "customers"), "email"))
        version = engine.schema_version
        engine.refresh()
        self.assertEqual(engine.schema_version, version)
        self.assertEqual(len(version), 12)
        self.assertIsNotNone(engine.store)

    def test_without_metadata(self) -> None:
        """No metadata root means an empty policy and no store."""
        engine = SqlRag(self.conn)
        self.assertIsNone(engine.store)
        self.assertEqual(engine.annotated.metadata.tables, ())

    def test_scope_filters(self) -> None:
        """Scope mappings become validated filters; bad mappings are configuration errors."""
        engine = SqlRag(self.conn, config=Config(scope=lambda table: ({"column": "region", "op": "eq", "value": "north"},) if table == "customers" else ()))
        customers = engine.catalog.table(TableRef(None, "customers"))
        self.assertEqual(engine.scope_filters(customers), (Filter("region", FilterOp.EQ, "north"),))
        self.assertEqual(engine.scope_filters(engine.catalog.table(TableRef(None, "orders"))), ())
        broken = SqlRag(self.conn, config=Config(scope=lambda table: ({"colum": "region", "op": "eq", "value": 1},)))
        with self.assertRaises(ConfigurationError):
            broken.scope_filters(customers)

    def test_dialect_and_paramstyle_handling(self) -> None:
        """Ambiguous drivers need an explicit dialect; an unknown paramstyle is refused."""
        with self.assertRaises(DialectDetectionError):
            SqlRag(fake_driver("pyodbc", "qmark")())
        with self.assertRaises(ConfigurationError):
            SqlRag(self.conn, paramstyle="dollar")
        engine = SqlRag(self.conn, dialect="sqlite3", paramstyle="named", config=Config(limits=Limits(max_rows=5)))
        self.assertEqual((engine.executor.paramstyle, engine.limits.max_rows), ("named", 5))

    def test_unknown_tool_envelope(self) -> None:
        """An unregistered tool name answers with an UnknownToolError envelope in both formats."""
        engine = SqlRag(self.conn)
        self.assertTrue(engine.tool_specs())
        self.assertEqual(engine.dispatch("no_such_tool", {})["error"]["type"], "UnknownToolError")
        self.assertTrue(engine.dispatch_text("no_such_tool", {}).startswith("error UnknownToolError"))


if __name__ == "__main__":
    unittest.main()
