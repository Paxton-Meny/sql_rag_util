"""Tests for merging metadata into the catalog."""

from __future__ import annotations

import pathlib
import unittest
from dataclasses import replace

from sql_rag_util.dialects import load
from sql_rag_util.config import Limits
from sql_rag_util.exceptions import MetadataFormatError, UnknownColumnError, UnknownConceptError, UnknownMeasureError
from sql_rag_util.executor import Executor
from sql_rag_util.metadata.annotate import annotate
from sql_rag_util.metadata.model import ColumnMeta, ConceptMeta, DeclaredRelationship, GlossaryEntry, MeasureMeta, Metadata, RelationshipMeta, TableMeta
from sql_rag_util.metadata.store import MetadataStore
from sql_rag_util.query.compile import compile_query
from sql_rag_util.query.spec import Filter, FilterOp, Measure, QuerySpec
from sql_rag_util.schema.introspect import introspect
from sql_rag_util.sql.render import render
from sql_rag_util.schema.model import TableRef
from tests.support.fixture import build_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"
ORDERS = TableRef(None, "orders")
CUSTOMERS = TableRef(None, "customers")


class AnnotateTest(unittest.TestCase):
    """The fixture metadata annotates the fixture database."""

    def setUp(self) -> None:
        conn = build_fixture()
        self.addCleanup(conn.close)
        self.dialect = load("sqlite")
        self.catalog = introspect(Executor(conn, "qmark"), self.dialect)
        self.metadata = MetadataStore(FIXTURES).load()

    def test_fixture_annotates(self) -> None:
        """Policy, searchable columns, renames, declared relationships, concepts, measures, and version."""
        annotated = annotate(self.catalog, self.metadata, self.dialect)
        self.assertTrue(annotated.policy.is_hidden(ORDERS, "notes"))
        self.assertTrue(annotated.policy.is_sensitive(CUSTOMERS, "email"))
        self.assertTrue(annotated.policy.is_hidden(CUSTOMERS, "password_hash"))
        self.assertEqual(annotated.searchable[CUSTOMERS], ("name",))
        names = {r.name: r for r in annotated.catalog.relationships_of(ORDERS)}
        self.assertIn("customer", names)
        self.assertNotIn("customers_via_customer_id", names)
        self.assertEqual(names["customer"].description, "The buyer.")
        self.assertEqual(names["shipments"].description, "Shipments for this order.")
        self.assertEqual((names["order_events"].origin, names["order_events"].cardinality, names["order_events"].pairs), ("declared", "to_many", (("id", "order_id"),)))
        filters = annotated.concept_filters(ORDERS, ("active", "last_30_days"))
        self.assertEqual([f.op for f in filters], [FilterOp.IN, FilterOp.SINCE_DAYS])
        self.assertEqual(annotated.measure(ORDERS, "revenue"), Measure("sum", "amount", "revenue"))
        self.assertEqual(len(annotated.version), 12)
        with self.assertRaises(UnknownConceptError) as ctx:
            annotated.concept_filters(ORDERS, ("archived",))
        self.assertEqual(ctx.exception.suggestions, ("active", "last_30_days"))
        with self.assertRaises(UnknownMeasureError):
            annotated.measure(CUSTOMERS, "revenue")

    def _hide(self, hidden: dict[str, tuple[str, ...]]) -> Metadata:
        tables = []
        for meta in self.metadata.tables:
            names = hidden.get(meta.table, ())
            kept = tuple(c for c in meta.columns if c.name not in names)
            tables.append(replace(meta, columns=kept + tuple(ColumnMeta(n, "", frozenset({"hidden"})) for n in names)))
        return replace(self.metadata, tables=tuple(tables))

    def test_hidden_columns_leave_the_agent_catalog(self) -> None:
        """Hidden columns, keys through them, and foreign keys on them are absent, while joins still work."""
        annotated = annotate(self.catalog, self._hide({"customers": ("id",), "orders": ("customer_id",)}), self.dialect)
        customers = annotated.catalog.table(CUSTOMERS)
        self.assertEqual([c.name for c in customers.columns], ["name", "email", "region"])
        self.assertEqual(customers.primary_key, ())
        self.assertFalse(any(fk.referenced == CUSTOMERS or "customer_id" in fk.columns for fk in annotated.catalog.foreign_keys))
        self.assertEqual(self.catalog.table(CUSTOMERS).primary_key, ("id",))

        def compiled(spec: QuerySpec) -> str:
            return render(compile_query(self.dialect, annotated.catalog, annotated.policy, spec, Limits()).statement, "qmark")[0]

        self.assertIn('LEFT JOIN "customers" AS "t1" ON "t0"."customer_id" = "t1"."id"', compiled(QuerySpec("orders", columns=["id", "customer.name"])))
        self.assertTrue(compiled(QuerySpec("customers")).endswith('ORDER BY "t0"."name" LIMIT ?'))
        for spec in (QuerySpec("orders", columns=["customer_id"]), QuerySpec("orders", columns=["id", "customer.id"]), QuerySpec("orders", filters=[Filter("customer_id", "eq", 1)])):
            with self.subTest(spec=spec):
                with self.assertRaises(UnknownColumnError) as ctx:
                    compiled(spec)
                self.assertNotIn("customer_id", ctx.exception.suggestions)
                self.assertNotIn("id", ctx.exception.suggestions)

    def test_every_column_hidden_is_an_error(self) -> None:
        """A table with nothing left to show fails at load rather than at query time."""
        names = tuple(c.name for c in self.catalog.table(CUSTOMERS).columns)
        with self.assertRaisesRegex(MetadataFormatError, "every column of customers is hidden"):
            annotate(self.catalog, self._hide({"customers": names}), self.dialect)

    def test_version_changes_with_metadata(self) -> None:
        """Editing metadata changes the version; the same inputs give the same version."""
        first = annotate(self.catalog, self.metadata, self.dialect).version
        self.assertEqual(annotate(self.catalog, self.metadata, self.dialect).version, first)
        edited = replace(self.metadata, glossary=self.metadata.glossary + (GlossaryEntry("Rush", "Expedited order."),))
        self.assertNotEqual(annotate(self.catalog, edited, self.dialect).version, first)

    def test_rejections_name_the_file(self) -> None:
        """Each invalid reference raises a MetadataFormatError naming its file."""
        base = TableMeta("orders", "p")
        cases = {
            "tables/ghost.md": Metadata(tables=(TableMeta("ghost", "p"),)),
            "tables/orders.md": Metadata(tables=(replace(base, columns=(ColumnMeta("nope", "x"),)),)),
            "tables/orders.md ": Metadata(tables=(replace(base, columns=(ColumnMeta("Status", "x"),)),)),
            "searchable": Metadata(tables=(replace(base, columns=(ColumnMeta("amount", "x", frozenset({"searchable"})),)),)),
            "relationship": Metadata(tables=(replace(base, relationships=(RelationshipMeta("nope", "x"),)),)),
            "rename collision": Metadata(tables=(replace(base, relationships=(RelationshipMeta("shipments", "x", renames="customers_via_customer_id"),)),)),
            "concept sensitive": Metadata(tables=(TableMeta("customers", "p", columns=(ColumnMeta("email", "x", frozenset({"sensitive"})),), concepts=(ConceptMeta("mailed", "x", (Filter("email", "not_null"),)),)),)),
            "concept column collision": Metadata(tables=(replace(base, concepts=(ConceptMeta("status", "x", (Filter("id", "gt", 0),)),)),)),
            "measure kind": Metadata(tables=(replace(base, measures=(MeasureMeta("total", "x", Measure("sum", "status", "total")),)),)),
            "relationships.md": Metadata(relationships=(DeclaredRelationship("x", "orders", ("id",), "nowhere", ("id",), "to_one", "t"),)),
            "declared collision": Metadata(relationships=(DeclaredRelationship("shipments", "orders", ("id",), "shipments", ("order_id",), "to_many", "t"),)),
            "glossary.md": Metadata(glossary=(GlossaryEntry("T", "d", tables=("nowhere",)),)),
            "duplicate": Metadata(tables=(base, TableMeta("Orders", "p"))),
        }
        for label, metadata in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(MetadataFormatError) as ctx:
                    annotate(self.catalog, metadata, self.dialect)
                self.assertTrue(ctx.exception.path.endswith(".md"), ctx.exception.path)


if __name__ == "__main__":
    unittest.main()
