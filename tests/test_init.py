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


if __name__ == "__main__":
    unittest.main()
