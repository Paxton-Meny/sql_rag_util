"""Tests for relationship derivation."""

from __future__ import annotations

import unittest

from sql_rag_util.schema.model import ForeignKeyInfo, TableRef
from sql_rag_util.schema.relationships import derive_relationships

CUSTOMERS = TableRef(None, "customers")
ORDERS = TableRef(None, "orders")
EMPLOYEES = TableRef(None, "employees")


def _names(rels: tuple, source: TableRef) -> dict[str, tuple[str, str]]:
    return {r.name: (r.target.name, r.cardinality) for r in rels if r.source == source}


class DeriveRelationshipsTest(unittest.TestCase):
    """Names are table names when unique and via-forms when they would collide."""

    def test_single_key_gives_plain_names(self) -> None:
        """Forward is named after the target, reverse after the source."""
        rels = derive_relationships((ForeignKeyInfo(ORDERS, ("customer_id",), CUSTOMERS, ("id",)),))
        self.assertEqual(_names(rels, ORDERS), {"customers": ("customers", "to_one")})
        self.assertEqual(_names(rels, CUSTOMERS), {"orders": ("orders", "to_many")})
        forward = next(r for r in rels if r.source == ORDERS)
        self.assertEqual(forward.pairs, (("customer_id", "id"),))
        reverse = next(r for r in rels if r.source == CUSTOMERS)
        self.assertEqual(reverse.pairs, (("id", "customer_id"),))

    def test_two_keys_to_one_table_use_via_names_on_both_sides(self) -> None:
        """Neither key keeps the bare name, so the agent cannot pick the wrong one silently."""
        rels = derive_relationships(
            (
                ForeignKeyInfo(ORDERS, ("customer_id",), CUSTOMERS, ("id",)),
                ForeignKeyInfo(ORDERS, ("billing_customer_id",), CUSTOMERS, ("id",)),
            )
        )
        self.assertEqual(
            set(_names(rels, ORDERS)), {"customers_via_customer_id", "customers_via_billing_customer_id"}
        )
        self.assertEqual(set(_names(rels, CUSTOMERS)), {"orders_via_customer_id", "orders_via_billing_customer_id"})

    def test_self_reference_gets_cardinality_suffix(self) -> None:
        """A self-referential key yields two distinct names on the same table."""
        rels = derive_relationships((ForeignKeyInfo(EMPLOYEES, ("manager_id",), EMPLOYEES, ("id",)),))
        self.assertEqual(
            _names(rels, EMPLOYEES),
            {"employees_via_manager_id": ("employees", "to_one"), "employees_via_manager_id_to_many": ("employees", "to_many")},
        )

    def test_composite_pairs_keep_order(self) -> None:
        """Composite keys pair columns positionally on both directions."""
        shipments, events = TableRef(None, "shipments"), TableRef(None, "shipment_events")
        rels = derive_relationships((ForeignKeyInfo(events, ("order_id", "seq"), shipments, ("order_id", "seq")),))
        forward = next(r for r in rels if r.source == events)
        self.assertEqual(forward.pairs, (("order_id", "order_id"), ("seq", "seq")))


if __name__ == "__main__":
    unittest.main()
