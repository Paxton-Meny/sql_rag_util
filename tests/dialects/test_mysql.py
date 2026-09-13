"""Tests for the MySQL dialect."""

from __future__ import annotations

import unittest

from sql_rag_util.dialects import load
from sql_rag_util.schema.model import ColumnKind, TableRef
from sql_rag_util.sql.render import render
from sql_rag_util.sql.statement import sql


class MysqlDialectTest(unittest.TestCase):
    """Backtick quoting, COLUMN_TYPE kinds, and information_schema statements."""

    def setUp(self) -> None:
        self.dialect = load("mariadb")

    def test_quote_and_limit(self) -> None:
        """Backticks are doubled inside names and the limit is bound."""
        self.assertEqual(self.dialect.quote("a`b"), "`a``b`")
        statement = self.dialect.limited_select(sql("`a`"), sql("FROM `t`"), 10)
        self.assertEqual(render(statement, "format"), ("SELECT `a` FROM `t` LIMIT %s", (10,)))

    def test_kinds(self) -> None:
        """tinyint(1) is boolean, other integers are integer, and type text is folded."""
        cases = {
            "tinyint(1)": ColumnKind.BOOLEAN, "tinyint(4)": ColumnKind.INTEGER, "INT(11) unsigned": ColumnKind.INTEGER,
            "decimal(10,2)": ColumnKind.DECIMAL, "double": ColumnKind.FLOAT, "datetime": ColumnKind.DATETIME,
            "timestamp": ColumnKind.DATETIME, "date": ColumnKind.DATE, "time": ColumnKind.TIME,
            "json": ColumnKind.JSON, "varchar(80)": ColumnKind.TEXT, "enum('a','b')": ColumnKind.TEXT,
            "longtext": ColumnKind.TEXT, "varbinary(16)": ColumnKind.BINARY, "bit(1)": ColumnKind.BINARY,
            "geometry": ColumnKind.OTHER,
        }
        for native, kind in cases.items():
            with self.subTest(native=native):
                self.assertEqual(self.dialect.kind_of(native), kind)

    def test_tables_statement(self) -> None:
        """The default schema is DATABASE(); explicit schemas are bound in an IN list."""
        text, params = render(self.dialect.tables_statement(None), "format")
        self.assertIn("TABLE_SCHEMA = DATABASE()", text)
        self.assertEqual(params, ())
        text, params = render(self.dialect.tables_statement(("shop", "crm")), "format")
        self.assertIn("TABLE_SCHEMA IN (%s, %s)", text)
        self.assertEqual(params, ("shop", "crm"))

    def test_columns_and_foreign_keys_bind_the_table(self) -> None:
        """Schema and table names are bound, with NULL schema falling back to DATABASE()."""
        text, params = render(self.dialect.columns_statement(TableRef(None, "orders")), "format")
        self.assertEqual(params, (None, "orders"))
        self.assertIn("COALESCE(%s, DATABASE())", text)
        self.assertIn("ORDER BY c.ORDINAL_POSITION", text)
        text, params = render(self.dialect.foreign_keys_statement(TableRef("shop", "orders")), "format")
        self.assertEqual(params, ("shop", "orders"))
        self.assertIn("REFERENCED_TABLE_NAME IS NOT NULL", text)
        self.assertEqual(render(self.dialect.default_schema_statement(), "format"), ("SELECT DATABASE()", ()))


if __name__ == "__main__":
    unittest.main()
