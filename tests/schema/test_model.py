"""Tests for the catalog model."""

from __future__ import annotations

import dataclasses
import unittest

from sql_rag_util.schema.model import (
    Catalog,
    ColumnInfo,
    ColumnKind,
    Relationship,
    TableInfo,
    TableRef,
)

ORDERS = TableRef(None, "orders")
CUSTOMERS = TableRef("shop", "customers")


def _orders() -> TableInfo:
    return TableInfo(
        ORDERS,
        (
            ColumnInfo("id", "INTEGER", ColumnKind.INTEGER, False, pk_position=1),
            ColumnInfo("tenant", "INTEGER", ColumnKind.INTEGER, False, pk_position=2),
            ColumnInfo("status", "TEXT", ColumnKind.TEXT, True),
        ),
    )


class ModelTest(unittest.TestCase):
    """Value types are frozen, hashable, and answer lookups."""

    def test_frozen_and_hashable(self) -> None:
        """Instances refuse mutation and can be set members."""
        table = _orders()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            table.ref = CUSTOMERS  # type: ignore[misc]
        self.assertEqual(len({ORDERS, TableRef(None, "orders")}), 1)

    def test_qualified_name(self) -> None:
        """A schema-qualified ref renders with a dot, a bare one without."""
        self.assertEqual(ORDERS.qualified, "orders")
        self.assertEqual(CUSTOMERS.qualified, "shop.customers")

    def test_primary_key_order_follows_positions(self) -> None:
        """Primary key columns come back in key order, not column order."""
        self.assertEqual(_orders().primary_key, ("id", "tenant"))

    def test_column_lookup_is_exact(self) -> None:
        """Lookup matches the exact name and returns None otherwise."""
        table = _orders()
        self.assertEqual(table.column("status").native_type, "TEXT")
        self.assertIsNone(table.column("Status"))

    def test_catalog_lookups(self) -> None:
        """Tables and relationships are found by ref."""
        rel = Relationship("customer", ORDERS, CUSTOMERS, (("customer_id", "id"),), "to_one", "foreign_key")
        catalog = Catalog("sqlite", (_orders(),), relationships=(rel,))
        self.assertIs(catalog.table(ORDERS), catalog.tables[0])
        self.assertIsNone(catalog.table(CUSTOMERS))
        self.assertEqual(catalog.relationships_of(ORDERS), (rel,))
        self.assertEqual(catalog.relationships_of(CUSTOMERS), ())

    def test_kind_groups(self) -> None:
        """Kind enumerations are string enums with stable values."""
        self.assertEqual(ColumnKind.TEXT, "text")
        self.assertEqual(ColumnKind("datetime"), ColumnKind.DATETIME)


if __name__ == "__main__":
    unittest.main()
