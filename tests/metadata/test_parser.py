"""Tests for the per-file metadata parsers."""

from __future__ import annotations

import pathlib
import unittest

from sql_rag_util.exceptions import MetadataFormatError
from sql_rag_util.metadata.parser import parse_glossary, parse_project, parse_relationships, parse_table
from sql_rag_util.query.spec import AggregateFn, FilterOp

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


def _read(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text()


class ParseTableTest(unittest.TestCase):
    """Table files parse into TableMeta with every section."""

    def test_orders_fixture(self) -> None:
        """Header, columns with flags and subs, relationships, concepts, and measures are read."""
        meta = parse_table(_read("tables", "orders.md"), "tables/orders.md", "orders")
        self.assertEqual((meta.table, meta.purpose, meta.synonyms), ("orders", "One row per customer order.", ("purchase", "sale")))
        self.assertTrue(meta.description.startswith("Amounts are"))
        status = meta.column("status")
        self.assertEqual((status.values, status.synonyms, status.flags), (("open", "paid", "shipped", "cancelled"), ("state", "stage"), frozenset()))
        self.assertEqual(meta.column("notes").flags, frozenset({"hidden"}))
        self.assertEqual(meta.column("created_at").source, "agent, 2026-09-13")
        self.assertEqual(meta.relationships[0].renames, "customers_via_customer_id")
        self.assertIsNone(meta.relationships[1].renames)
        active = meta.concepts[0]
        self.assertEqual((active.name, active.where[0].op, active.where[0].value), ("active", FilterOp.IN, ("open", "paid")))
        self.assertEqual(meta.concepts[1].where[0].op, FilterOp.SINCE_DAYS)
        self.assertEqual((meta.measures[0].expr.fn, meta.measures[0].expr.column, meta.measures[0].expr.name), (AggregateFn.SUM, "amount", "revenue"))
        self.assertIsNone(meta.measures[1].expr.column)

    def test_customers_fixture_flags(self) -> None:
        """Flag combinations parse and optional sections may be absent."""
        meta = parse_table(_read("tables", "customers.md"), "tables/customers.md", "customers")
        self.assertEqual(meta.column("email").flags, frozenset({"sensitive"}))
        self.assertEqual(meta.concepts, ())

    def test_rejections(self) -> None:
        """Stem mismatch, unknown keys, flags, sections, and bad JSON shapes fail with lines."""
        base = "# orders\n\nformat: 1\npurpose: p\n"
        cases = {
            "# other\n\nformat: 1\npurpose: p\n": 1,
            "# orders\n\nformat: 1\n": 3,
            base.replace("purpose: p\n", "purpose: p\nowner: me\n"): 5,
            base + "\n## Extra\n": 6,
            base + "\n## Columns\n\n- a [secret]: x\n": 8,
            base + "\n## Columns\n\n- a [hidden, sensitive]: x\n": 8,
            base + "\n## Columns\n\n- a [searchable, sensitive]: x\n": 8,
            base + "\n## Columns\n\n- a [fulltext, hidden]: x\n": 8,
            base + "\n## Columns\n\n- a [fulltext, sensitive]: x\n": 8,
            base + "\n## Columns\n\n- a: x\n  - nope: 1\n": 9,
            base + "\n## Concepts\n\n- Active: x\n  - where: []\n": 8,
            base + "\n## Concepts\n\n- active: x\n": 8,
            base + "\n## Concepts\n\n- active: x\n  - where: []\n": 9,
            base + "\n## Concepts\n\n- active: x\n  - where: [{\"column\": \"a\", \"op\": \"like\", \"value\": 1}]\n": 9,
            base + "\n## Measures\n\n- m: x\n  - expr: {\"fn\": \"sum\"}\n": 9,
            base + "\n## Measures\n\n- m: x\n  - expr: {\"fn\": \"count\", \"extra\": 1}\n": 9,
            base + "\n## Relationships\n\n- a [x]: y\n": 8,
        }
        for text, line in cases.items():
            with self.subTest(text=text):
                with self.assertRaises(MetadataFormatError) as ctx:
                    parse_table(text, "tables/orders.md", "orders")
                self.assertEqual(ctx.exception.line, line, str(ctx.exception))


class OtherFilesTest(unittest.TestCase):
    """project.md, relationships.md, and glossary.md parse and reject."""

    def test_project(self) -> None:
        """Settings parse with defaults and caps."""
        meta = parse_project(_read("project.md"), "project.md")
        self.assertEqual((meta.value_index, meta.value_index_max_distinct, meta.samples_per_column), (True, 50, 2))
        defaults = parse_project("# project\n\nformat: 1\n", "project.md")
        self.assertEqual((defaults.value_index, defaults.value_index_max_distinct, defaults.samples_per_column, defaults.description), (False, 200, 3, ""))
        for text in ("# proj\n\nformat: 1\n", "# project\n\nformat: 1\nvalue_index: yes\n", "# project\n\nformat: 1\nsamples_per_column: 11\n", "# project\n\nformat: 1\n\n## Notes\n"):
            with self.subTest(text=text):
                with self.assertRaises(MetadataFormatError):
                    parse_project(text, "project.md")

    def test_relationships(self) -> None:
        """Declared relationships carry both sides and cardinality."""
        rels = parse_relationships(_read("relationships.md"), "relationships.md")
        self.assertEqual(rels[0].name, "order_events")
        self.assertEqual((rels[0].from_table, rels[0].from_columns, rels[0].to_table, rels[0].to_columns), ("orders", ("id",), "shipment_events", ("order_id",)))
        self.assertEqual(rels[0].cardinality, "to_many")
        head = "# relationships\n\nformat: 1\n\n## r\n\n"
        for text, line in {
            head + "from: a (x)\nto: b (y)\ncardinality: to_many\n": 5,
            head + "from: a (x)\nto: b (y, z)\ncardinality: to_many\ntext: t\n": 8,
            head + "from: a x\nto: b (y)\ncardinality: to_many\ntext: t\n": 7,
            head + "from: a (x)\nto: b (y)\ncardinality: many\ntext: t\n": 9,
        }.items():
            with self.subTest(text=text):
                with self.assertRaises(MetadataFormatError) as ctx:
                    parse_relationships(text, "relationships.md")
                self.assertEqual(ctx.exception.line, line)

    def test_glossary(self) -> None:
        """Terms carry synonyms and tables; duplicates are refused case-insensitively."""
        terms = parse_glossary(_read("glossary.md"), "glossary.md")
        self.assertEqual(terms[0].term, "SKU")
        self.assertEqual(terms[0].synonyms, ("product code", "item number"))
        self.assertEqual(terms[1].tables, ("customers",))
        with self.assertRaises(MetadataFormatError) as ctx:
            parse_glossary("# glossary\n\nformat: 1\n\n## Terms\n\n- A: x\n- a: y\n", "glossary.md")
        self.assertEqual(ctx.exception.line, 8)


if __name__ == "__main__":
    unittest.main()
