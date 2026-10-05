"""Tests for name resolution."""

from __future__ import annotations

import unittest

from sql_rag_util.dialects import load
from sql_rag_util.exceptions import UnknownColumnError, UnknownRelationshipError, UnknownTableError
from sql_rag_util.executor import Executor
from sql_rag_util.schema.introspect import introspect
from sql_rag_util.schema.model import Catalog, ColumnInfo, ColumnKind, TableInfo, TableRef
from sql_rag_util.schema.resolve import agent_name, closest, resolve_column, resolve_relationship, resolve_table
from tests.support.fixture import fixture_connection


class ResolveTest(unittest.TestCase):
    """Exact, then unique case-insensitive, then suggestions."""

    def setUp(self) -> None:
        conn = fixture_connection(self)
        self.catalog = introspect(Executor(conn, "qmark"), load("sqlite"))

    def test_table_resolution(self) -> None:
        """Exact and case-folded names resolve; a typo raises with close matches."""
        self.assertEqual(resolve_table(self.catalog, "orders").ref.name, "orders")
        self.assertEqual(resolve_table(self.catalog, "Orders").ref.name, "orders")
        with self.assertRaises(UnknownTableError) as ctx:
            resolve_table(self.catalog, "ordr")
        self.assertIn("orders", ctx.exception.suggestions)
        self.assertIn("did you mean", str(ctx.exception))

    def test_column_and_relationship_resolution(self) -> None:
        """Columns and relationships resolve the same way and name the table in errors."""
        orders = resolve_table(self.catalog, "orders")
        self.assertEqual(resolve_column(orders, "STATUS").name, "status")
        with self.assertRaises(UnknownColumnError) as ctx:
            resolve_column(orders, "stats")
        self.assertIn("orders", str(ctx.exception))
        self.assertEqual(resolve_relationship(self.catalog, orders, "shipments").target.name, "shipments")
        with self.assertRaises(UnknownRelationshipError) as ctx:
            resolve_relationship(self.catalog, orders, "customers")
        self.assertIn("customers_via_customer_id", ctx.exception.suggestions)

    def test_qualified_names_when_ambiguous(self) -> None:
        """A table name shared by two schemas is exposed qualified and resolves by either form when unique."""
        col = (ColumnInfo("id", "int", ColumnKind.INTEGER, False, 1),)
        catalog = Catalog("mysql", (TableInfo(TableRef("shop", "orders"), col), TableInfo(TableRef("crm", "orders"), col), TableInfo(TableRef("crm", "leads"), col)))
        self.assertEqual(agent_name(catalog, TableRef("shop", "orders")), "shop.orders")
        self.assertEqual(agent_name(catalog, TableRef("crm", "leads")), "leads")
        self.assertEqual(resolve_table(catalog, "crm.orders").ref.schema, "crm")
        self.assertEqual(resolve_table(catalog, "crm.leads").ref.name, "leads")
        with self.assertRaises(UnknownTableError):
            resolve_table(catalog, "orders")

    def test_closest_folds_case(self) -> None:
        """Suggestions include case-insensitive near matches without duplicates."""
        self.assertEqual(closest("CUSTOMER", ["customers", "orders"]), ("customers",))
        self.assertEqual(closest("zzz", ["customers"]), ())


if __name__ == "__main__":
    unittest.main()
