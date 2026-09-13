"""Tests for the SQLite dialect."""

from __future__ import annotations

import sqlite3
import unittest

from sql_rag_util.dialects import load
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.schema.model import ColumnKind, TableRef
from sql_rag_util.sql.render import render


class SqliteDialectTest(unittest.TestCase):
    """Quoting, kinds, and introspection statements that run against a live database."""

    def setUp(self) -> None:
        self.dialect = load("sqlite")

    def test_kinds_follow_declared_types_then_affinity(self) -> None:
        """Declared temporal and boolean types win; otherwise the affinity rules apply."""
        cases = {
            "INTEGER": ColumnKind.INTEGER, "BIGINT": ColumnKind.INTEGER, "VARCHAR(20)": ColumnKind.TEXT,
            "CLOB": ColumnKind.TEXT, "BLOB": ColumnKind.BINARY, "": ColumnKind.BINARY,
            "REAL": ColumnKind.FLOAT, "DOUBLE PRECISION": ColumnKind.FLOAT, "NUMERIC(10,2)": ColumnKind.DECIMAL,
            "BOOLEAN": ColumnKind.BOOLEAN, "DATETIME": ColumnKind.DATETIME, "TIMESTAMP": ColumnKind.DATETIME,
            "DATE": ColumnKind.DATE, "TIME": ColumnKind.TIME, "JSON": ColumnKind.JSON, "uuid": ColumnKind.UUID,
            "STRING": ColumnKind.DECIMAL,
        }
        for native, kind in cases.items():
            with self.subTest(native=native):
                self.assertEqual(self.dialect.kind_of(native), kind)

    def test_statements_run_live(self) -> None:
        """Introspection statements execute on sqlite3 and return the documented shapes."""
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.executescript(
            "CREATE TABLE parents (id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
            "CREATE TABLE kids (id INTEGER, tenant INTEGER, parent_id INTEGER REFERENCES parents,"
            " nick TEXT, PRIMARY KEY (tenant, id));"
        )
        tables = conn.execute(*render(self.dialect.tables_statement(None), "qmark")).fetchall()
        self.assertEqual(tables, [(None, "kids", None), (None, "parents", None)])
        columns = conn.execute(*render(self.dialect.columns_statement(TableRef(None, "kids")), "qmark")).fetchall()
        self.assertEqual(
            columns,
            [("id", "INTEGER", 1, 2), ("tenant", "INTEGER", 1, 1), ("parent_id", "INTEGER", 1, None), ("nick", "TEXT", 1, None)],
        )
        fks = conn.execute(*render(self.dialect.foreign_keys_statement(TableRef(None, "kids")), "qmark")).fetchall()
        self.assertEqual(fks, [(0, 0, "parent_id", None, "parents", None)])
        probe = conn.execute(*render(self.dialect.capability_probe_statement(), "qmark")).fetchall()
        self.assertTrue(set(probe) <= {('soundex',), ('levenshtein',)}, probe)

    def test_probe_maps_registered_functions(self) -> None:
        """Function names from the probe map to capabilities; unknown names are ignored."""
        self.assertEqual(
            self.dialect.probe_capabilities(["SOUNDEX", "levenshtein", "other"]),
            frozenset({Capability.SOUNDEX, Capability.LEVENSHTEIN}),
        )
        self.assertIn(Capability.CASE_INSENSITIVE_LIKE, self.dialect.static_capabilities)


if __name__ == "__main__":
    unittest.main()
