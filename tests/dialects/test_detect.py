"""Tests for dialect detection and the registry."""

from __future__ import annotations

import sqlite3
import unittest

from sql_rag_util import dialects
from sql_rag_util.dialects.detect import detect
from sql_rag_util.exceptions import DialectDetectionError, UnsupportedDialectError
from tests.support.fakes import fake_driver


class DetectTest(unittest.TestCase):
    """Detection maps known drivers and refuses ambiguous or unknown ones."""

    def test_known_drivers(self) -> None:
        """Each driver maps to its dialect and reports its paramstyle."""
        cases = {
            "psycopg": ("postgres", "pyformat"),
            "pymysql": ("mysql", "pyformat"),
            "MySQLdb": ("mysql", "format"),
            "pymssql": ("mssql", "pyformat"),
            "pg8000": ("postgres", "format"),
        }
        for driver, (dialect, style) in cases.items():
            with self.subTest(driver=driver):
                found = detect(fake_driver(driver, style)())
                self.assertEqual((found.dialect, found.paramstyle, found.driver), (dialect, style, driver))

    def test_live_sqlite(self) -> None:
        """The real sqlite3 module is detected with its qmark paramstyle."""
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        found = detect(conn)
        self.assertEqual((found.dialect, found.paramstyle), ("sqlite", "qmark"))

    def test_missing_or_bad_paramstyle_is_none(self) -> None:
        """A driver without a valid paramstyle attribute yields None so the dialect default applies."""
        self.assertIsNone(detect(fake_driver("mariadb", None)()).paramstyle)
        self.assertIsNone(detect(fake_driver("pymysql", "dollar")()).paramstyle)

    def test_ambiguous_and_unknown_require_explicit_dialect(self) -> None:
        """pyodbc and unknown drivers raise with suggestions; an explicit dialect wins."""
        for driver in ("pyodbc", "somethingelse"):
            with self.subTest(driver=driver):
                conn = fake_driver(driver, "qmark")()
                with self.assertRaises(DialectDetectionError) as ctx:
                    detect(conn)
                self.assertIn("mssql", ctx.exception.suggestions)
                self.assertEqual(detect(conn, dialect="mssql").dialect, "mssql")

    def test_explicit_dialect_overrides_detection(self) -> None:
        """A caller's dialect wins even when the driver is known."""
        self.assertEqual(detect(fake_driver("pymysql", "format")(), dialect="mssql").dialect, "mssql")


class RegistryTest(unittest.TestCase):
    """Names and aliases resolve; unknown names are refused before any import."""

    def test_aliases_and_canonical_names(self) -> None:
        """Aliases fold to supported names, case-insensitively."""
        for alias, name in (("PostgreSQL", "postgres"), ("MariaDB", "mysql"), ("sqlserver", "mssql"), ("sqlite3", "sqlite")):
            with self.subTest(alias=alias):
                self.assertEqual(dialects.canonical_name(alias), name)

    def test_unknown_name_is_refused(self) -> None:
        """An unsupported name raises with the supported list as suggestions."""
        with self.assertRaises(UnsupportedDialectError) as ctx:
            dialects.load("oracle")
        self.assertEqual(ctx.exception.suggestions, dialects.SUPPORTED)


if __name__ == "__main__":
    unittest.main()
