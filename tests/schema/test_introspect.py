"""Tests for catalog introspection."""

from __future__ import annotations

import unittest

from sql_rag_util.dialects import load
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.executor import Executor
from sql_rag_util.schema.introspect import fingerprint_of, introspect
from sql_rag_util.schema.model import ColumnKind, TableRef
from tests.support.fakes import FakeConnection, FakeCursor
from tests.support.fixture import build_fixture


class SqliteIntrospectTest(unittest.TestCase):
    """The fixture database introspects into the expected catalog."""

    def setUp(self) -> None:
        self.catalog = introspect(Executor(build_fixture(), "qmark"), load("sqlite"))

    def test_tables_columns_and_keys(self) -> None:
        """Tables, kinds, nullability, and composite primary keys are read."""
        self.assertEqual([t.ref.name for t in self.catalog.tables], ["customers", "employees", "orders", "shipment_events", "shipments"])
        orders = self.catalog.table(TableRef(None, "orders"))
        self.assertEqual(orders.primary_key, ("id",))
        self.assertEqual(orders.column("amount").kind, ColumnKind.DECIMAL)
        self.assertEqual(orders.column("created_at").kind, ColumnKind.DATETIME)
        self.assertFalse(orders.column("status").nullable)
        self.assertEqual(self.catalog.table(TableRef(None, "shipments")).primary_key, ("order_id", "seq"))
        self.assertIsNone(orders.row_estimate)

    def test_implied_and_composite_foreign_keys(self) -> None:
        """A key that names no target column resolves to the parent primary key; composites keep order."""
        by_source = {(fk.table.name, fk.columns): fk for fk in self.catalog.foreign_keys}
        self.assertEqual(by_source[("orders", ("customer_id",))].referenced_columns, ("id",))
        self.assertEqual(by_source[("shipment_events", ("order_id", "seq"))].referenced_columns, ("order_id", "seq"))
        self.assertEqual(by_source[("employees", ("manager_id",))].referenced, TableRef(None, "employees"))

    def test_relationships_capabilities_fingerprint(self) -> None:
        """Relationships are derived, capabilities merged, and the fingerprint is stable."""
        names = {r.name for r in self.catalog.relationships_of(TableRef(None, "orders"))}
        self.assertEqual(names, {"customers_via_customer_id", "customers_via_billing_customer_id", "shipments"})
        self.assertIn(Capability.CASE_INSENSITIVE_LIKE, self.catalog.capabilities)
        again = introspect(Executor(build_fixture(), "qmark"), load("sqlite"))
        self.assertEqual(self.catalog.fingerprint, again.fingerprint)
        self.assertEqual(len(self.catalog.fingerprint), 16)


class FakeDriverIntrospectTest(unittest.TestCase):
    """Rows shaped like information_schema answers assemble the same way."""

    def test_default_schema_is_folded_and_estimates_are_kept(self) -> None:
        """The default schema becomes None on refs; negative estimates become None."""
        cursors = [
            FakeCursor(rows=[("public",)]),
            FakeCursor(rows=[("public", "a", 12), ("public", "b", -1)]),
            FakeCursor(rows=[("id", "integer", False, 1)]),
            FakeCursor(rows=[("id", "integer", False, 1), ("a_id", "integer", True, None)]),
            FakeCursor(rows=[]),
            FakeCursor(rows=[("b_a_fk", 1, "a_id", "public", "a", "id")]),
            FakeCursor(rows=[("pg_trgm",)]),
        ]
        catalog = introspect(Executor(FakeConnection(cursors), "format"), load("postgres"))
        self.assertEqual([t.ref for t in catalog.tables], [TableRef(None, "a"), TableRef(None, "b")])
        self.assertEqual([t.row_estimate for t in catalog.tables], [12, None])
        self.assertEqual(catalog.foreign_keys[0].referenced, TableRef(None, "a"))
        self.assertEqual(catalog.foreign_keys[0].name, "b_a_fk")
        self.assertIn(Capability.TRIGRAM, catalog.capabilities)
        self.assertIn(Capability.ROW_ESTIMATE, catalog.capabilities)

    def test_explicit_schemas_keep_names_and_skip_unloaded_targets(self) -> None:
        """With explicit schemas, refs keep their schema and a key to an unloaded table is dropped."""
        cursors = [
            FakeCursor(rows=[("shop", "orders", 5)]),
            FakeCursor(rows=[("id", "int", False, 1)]),
            FakeCursor(rows=[("fk", 1, "cust", "crm", "customers", "id")]),
        ]
        catalog = introspect(Executor(FakeConnection(cursors), "format"), load("mysql"), schemas=("shop",), include_row_estimates=False)
        self.assertEqual(catalog.tables[0].ref, TableRef("shop", "orders"))
        self.assertIsNone(catalog.tables[0].row_estimate)
        self.assertEqual(catalog.foreign_keys, ())

    def test_fingerprint_ignores_estimates(self) -> None:
        """Only structure feeds the fingerprint."""
        catalog = introspect(Executor(build_fixture(), "qmark"), load("sqlite"))
        self.assertEqual(fingerprint_of(catalog.tables, catalog.foreign_keys), catalog.fingerprint)


if __name__ == "__main__":
    unittest.main()
