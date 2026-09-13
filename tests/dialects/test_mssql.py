"""Tests for the SQL Server dialect."""

from __future__ import annotations

import unittest

from sql_rag_util.dialects import load
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.schema.model import ColumnKind, TableRef
from sql_rag_util.sql.render import render
from sql_rag_util.sql.statement import sql


class MssqlDialectTest(unittest.TestCase):
    """Bracket quoting, bound TOP, DATA_TYPE kinds, and INFORMATION_SCHEMA statements."""

    def setUp(self) -> None:
        self.dialect = load("sqlserver")

    def test_quote_and_top(self) -> None:
        """Closing brackets are doubled and TOP takes a bound value before the select list."""
        self.assertEqual(self.dialect.quote("a]b"), "[a]]b]")
        statement = self.dialect.limited_select(sql("[a]"), sql("FROM [t] ORDER BY [a]"), 7)
        self.assertEqual(render(statement, "qmark"), ("SELECT TOP (?) [a] FROM [t] ORDER BY [a]", (7,)))

    def test_kinds(self) -> None:
        """bit is boolean, rowversion and timestamp are binary, uniqueidentifier is uuid."""
        cases = {
            "bit": ColumnKind.BOOLEAN, "int": ColumnKind.INTEGER, "money": ColumnKind.DECIMAL,
            "float": ColumnKind.FLOAT, "datetime2": ColumnKind.DATETIME, "smalldatetime": ColumnKind.DATETIME,
            "date": ColumnKind.DATE, "time": ColumnKind.TIME, "timestamp": ColumnKind.BINARY,
            "rowversion": ColumnKind.BINARY, "uniqueidentifier": ColumnKind.UUID, "nvarchar": ColumnKind.TEXT,
            "xml": ColumnKind.TEXT, "varbinary": ColumnKind.BINARY, "hierarchyid": ColumnKind.OTHER,
        }
        for native, kind in cases.items():
            with self.subTest(native=native):
                self.assertEqual(self.dialect.kind_of(native), kind)

    def test_introspection_statements(self) -> None:
        """Default schema is SCHEMA_NAME(); table names are bound; both FK sides join by position."""
        text, params = render(self.dialect.tables_statement(None), "qmark")
        self.assertIn("t.TABLE_SCHEMA = SCHEMA_NAME()", text)
        self.assertIn("sys.partitions", text)
        self.assertEqual(params, ())
        text, params = render(self.dialect.columns_statement(TableRef("dbo", "Orders")), "qmark")
        self.assertEqual(params, ("dbo", "Orders"))
        self.assertIn("CONSTRAINT_TYPE = 'PRIMARY KEY'", text)
        text, params = render(self.dialect.foreign_keys_statement(TableRef(None, "Orders")), "qmark")
        self.assertEqual(params, (None, "Orders"))
        self.assertIn("r.ORDINAL_POSITION = k.ORDINAL_POSITION", text)
        self.assertEqual(self.dialect.static_capabilities, frozenset({Capability.SOUNDEX, Capability.DIFFERENCE, Capability.FULLTEXT, Capability.ROW_ESTIMATE}))


if __name__ == "__main__":
    unittest.main()
