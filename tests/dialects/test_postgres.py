"""Tests for the PostgreSQL dialect."""

from __future__ import annotations

import unittest

from sql_rag_util.dialects import load
from sql_rag_util.dialects.capabilities import Capability
from sql_rag_util.schema.model import ColumnKind, TableRef
from sql_rag_util.sql.render import render


class PostgresDialectTest(unittest.TestCase):
    """ILIKE matching, udt-aware kinds, information_schema statements, extension probe."""

    def setUp(self) -> None:
        self.dialect = load("postgresql")

    def test_ilike_predicates(self) -> None:
        """Substring and prefix predicates use ILIKE with the fixed escape character."""
        text, params = render(self.dialect.contains('"c"', "a_b"), "format")
        self.assertEqual((text, params), ('"c" ILIKE %s ESCAPE \'!\'', ("%a!_b%",)))
        self.assertEqual(render(self.dialect.starts_with('"c"', "x"), "format")[1], ("x%",))

    def test_kinds(self) -> None:
        """Standard names and udt names both classify; interval is other."""
        cases = {
            "boolean": ColumnKind.BOOLEAN, "integer": ColumnKind.INTEGER, "int4": ColumnKind.INTEGER,
            "numeric": ColumnKind.DECIMAL, "double precision": ColumnKind.FLOAT,
            "timestamp with time zone": ColumnKind.DATETIME, "date": ColumnKind.DATE,
            "time without time zone": ColumnKind.TIME, "uuid": ColumnKind.UUID, "jsonb": ColumnKind.JSON,
            "character varying": ColumnKind.TEXT, "text": ColumnKind.TEXT, "citext": ColumnKind.TEXT,
            "bytea": ColumnKind.BINARY, "interval": ColumnKind.OTHER, "my_enum": ColumnKind.OTHER,
        }
        for native, kind in cases.items():
            with self.subTest(native=native):
                self.assertEqual(self.dialect.kind_of(native), kind)

    def test_introspection_statements(self) -> None:
        """Default schema is current_schema(); FK sides match on position_in_unique_constraint."""
        text, params = render(self.dialect.tables_statement(("public",)), "format")
        self.assertIn("t.table_schema IN (%s)", text)
        self.assertIn("reltuples", text)
        self.assertEqual(params, ("public",))
        text, params = render(self.dialect.columns_statement(TableRef(None, "orders")), "format")
        self.assertEqual(params, (None, "orders"))
        self.assertIn("udt_name", text)
        text, params = render(self.dialect.foreign_keys_statement(TableRef(None, "orders")), "format")
        self.assertIn("position_in_unique_constraint", text)
        self.assertEqual(render(self.dialect.capability_probe_statement(), "format")[0], "SELECT extname FROM pg_catalog.pg_extension WHERE extname IN ('pg_trgm', 'fuzzystrmatch')")

    def test_probe_maps_extensions(self) -> None:
        """pg_trgm gives trigram; fuzzystrmatch gives levenshtein, soundex, and difference."""
        self.assertEqual(self.dialect.probe_capabilities(["pg_trgm"]), frozenset({Capability.TRIGRAM}))
        self.assertEqual(
            self.dialect.probe_capabilities(["fuzzystrmatch", "plpgsql"]),
            frozenset({Capability.LEVENSHTEIN, Capability.SOUNDEX, Capability.DIFFERENCE}),
        )


if __name__ == "__main__":
    unittest.main()
