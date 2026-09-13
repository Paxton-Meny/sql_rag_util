"""Tests for the exceptions module."""

from __future__ import annotations

import unittest

from sql_rag_util import exceptions


class HierarchyTest(unittest.TestCase):
    """Every exported exception derives from the package base."""

    def test_every_export_is_a_sqlrag_error(self) -> None:
        """Each name in ``__all__`` is a subclass of SqlRagError."""
        for name in exceptions.__all__:
            with self.subTest(name=name):
                cls = getattr(exceptions, name)
                self.assertTrue(issubclass(cls, exceptions.SqlRagError))

    def test_suggestions_and_type_name(self) -> None:
        """Suggestions are kept and the type name matches the class."""
        err = exceptions.UnknownTableError("no table ordr", suggestions=("orders",))
        self.assertEqual(err.suggestions, ("orders",))
        self.assertEqual(err.type_name, "UnknownTableError")
        self.assertEqual(str(err), "no table ordr")

    def test_metadata_format_error_carries_location(self) -> None:
        """The message is prefixed with path and line when a line is known."""
        err = exceptions.MetadataFormatError("unknown key", path="tables/orders.md", line=4)
        self.assertEqual(str(err), "tables/orders.md:4: unknown key")
        self.assertEqual((err.path, err.line), ("tables/orders.md", 4))
        whole = exceptions.MetadataFormatError("empty file", path="glossary.md")
        self.assertEqual(str(whole), "glossary.md: empty file")


if __name__ == "__main__":
    unittest.main()
