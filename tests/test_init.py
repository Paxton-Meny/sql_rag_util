"""Tests for the package root."""

from __future__ import annotations

import unittest

import sql_rag_util


class VersionTest(unittest.TestCase):
    """The package exposes a version string."""

    def test_version_is_semver_string(self) -> None:
        """The version has three dot-separated integer parts."""
        parts = sql_rag_util.__version__.split(".")
        self.assertEqual(len(parts), 3)
        for part in parts:
            with self.subTest(part=part):
                self.assertTrue(part.isdigit())

    def test_public_surface(self) -> None:
        """The facade, config, spec types, base error, and SQLite registration are exported."""
        for name in ("SqlRag", "Config", "Limits", "QuerySpec", "Filter", "Measure", "Order", "SqlRagError", "register_sqlite_functions"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(sql_rag_util, name))
                self.assertIn(name, sql_rag_util.__all__)


if __name__ == "__main__":
    unittest.main()
