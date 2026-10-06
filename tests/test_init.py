"""Tests for the package root."""

from __future__ import annotations

import pathlib
import tomllib
import unittest

import sql_rag_util

ROOT = pathlib.Path(__file__).resolve().parent.parent


class VersionTest(unittest.TestCase):
    """The package exposes a version string."""

    def test_version_is_semver_string(self) -> None:
        """The version has three dot-separated integer parts."""
        parts = sql_rag_util.__version__.split(".")
        self.assertEqual(len(parts), 3)
        for part in parts:
            with self.subTest(part=part):
                self.assertTrue(part.isdigit())

    def test_version_matches_the_project_metadata(self) -> None:
        """pyproject.toml and the package agree on the version, so a release cannot ship two numbers."""
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["version"], sql_rag_util.__version__)

    def test_project_metadata_is_complete_and_dependency_free(self) -> None:
        """No dependencies, an SPDX license expression with its file, no license classifier, and a typed marker."""
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["dependencies"], [])
        self.assertEqual(project["license"], "PolyForm-Noncommercial-1.0.0")
        self.assertTrue(all((ROOT / f).is_file() for f in project["license-files"]))
        self.assertFalse([c for c in project["classifiers"] if c.startswith("License ::")])
        self.assertIn("Typing :: Typed", project["classifiers"])
        self.assertTrue((ROOT / "sql_rag_util" / "py.typed").is_file())

    def test_public_surface(self) -> None:
        """The facade, config, spec types, base error, and SQLite registration are exported."""
        for name in ("SqlRag", "Config", "Limits", "QuerySpec", "Filter", "Measure", "Order", "SqlRagError", "register_sqlite_functions"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(sql_rag_util, name))
                self.assertIn(name, sql_rag_util.__all__)


if __name__ == "__main__":
    unittest.main()
