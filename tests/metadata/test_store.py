"""Tests for the contained metadata store."""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from sql_rag_util.atomic import atomic_write_text
from sql_rag_util.exceptions import MetadataFormatError, MetadataPathError
from sql_rag_util.metadata.model import ColumnMeta, TableMeta
from sql_rag_util.metadata.store import MetadataStore

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


class StoreTest(unittest.TestCase):
    """Loading, saving, containment, and atomicity."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "meta"
        shutil.copytree(FIXTURES, self.root)
        self.store = MetadataStore(self.root)

    def test_load_reads_every_file(self) -> None:
        """All four kinds of file are parsed and tables are sorted by name."""
        meta = self.store.load()
        self.assertTrue(meta.project.value_index)
        self.assertEqual([t.table for t in meta.tables], ["customers", "orders"])
        self.assertEqual(meta.relationships[0].name, "order_events")
        self.assertEqual(meta.glossary[0].term, "SKU")

    def test_missing_files_contribute_nothing(self) -> None:
        """An empty root loads as default metadata."""
        empty = MetadataStore(pathlib.Path(self.tmp.name) / "none")
        meta = empty.load()
        self.assertEqual((meta.tables, meta.relationships, meta.glossary, meta.project.value_index), ((), (), (), False))

    def test_save_and_remove_table(self) -> None:
        """Saving writes canonical text and reloads equal; removing deletes."""
        table = TableMeta("shipments", "One row per shipment.", columns=(ColumnMeta("carrier", "Carrier code.", frozenset({"searchable"})),))
        path = self.store.save_table(table)
        self.assertEqual(path, self.root / "tables" / "shipments.md")
        self.assertEqual(self.store.load().table("shipments"), table)
        self.assertEqual([p.name for p in path.parent.iterdir() if p.name.startswith(".")], [])
        self.assertTrue(self.store.remove_table("shipments"))
        self.assertFalse(self.store.remove_table("shipments"))

    def test_values_that_would_read_back_differently_are_never_written(self) -> None:
        """A rendering that parses to something else, or not at all, raises before touching the file."""
        path = self.root / "tables" / "orders.md"
        before = path.read_text()
        orders = self.store.load().table("orders")
        planted = ColumnMeta("status", "t\n- notes: visible")
        split = ColumnMeta("status", "t", values=("open,paid",))
        for column in (planted, split):
            with self.subTest(column=column):
                with self.assertRaisesRegex(MetadataFormatError, "tables/orders.md"):
                    self.store.save_table(replace(orders, columns=(column,)))
                self.assertEqual(path.read_text(), before)

    def test_bad_stems_and_escapes_are_refused(self) -> None:
        """Stems must be table names and paths must stay inside the root."""
        for stem in ("../x", "a b", "a.b.c", ""):
            with self.subTest(stem=stem):
                with self.assertRaises((MetadataFormatError, MetadataPathError)):
                    self.store.table_path(stem)
        with self.assertRaises(MetadataPathError):
            self.store.path("..", "outside.md")
        outside = pathlib.Path(self.tmp.name) / "outside"
        outside.mkdir()
        os.symlink(outside, self.root / "link")
        with self.assertRaises(MetadataPathError):
            self.store.path("link", "x.md")
        (self.root / "tables" / "bad name.md").write_text("# x\n\nformat: 1\n")
        with self.assertRaises(MetadataFormatError):
            self.store.load()

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_atomic_write_keeps_permissions_and_line_endings(self) -> None:
        """A rewrite keeps the file's mode, a new file gets the process default, and lines end in LF."""
        target = self.root / "project.md"
        target.chmod(0o640)
        atomic_write_text(target, "a\nb\n")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        self.assertEqual(target.read_bytes(), b"a\nb\n")
        control = self.root / "control.md"
        control.write_text("x")
        fresh = self.root / "fresh.md"
        atomic_write_text(fresh, "x")
        self.assertEqual(stat.S_IMODE(fresh.stat().st_mode), stat.S_IMODE(control.stat().st_mode))

    def test_atomic_write_leaves_no_temp_file_on_failure(self) -> None:
        """A failing write removes its temp file and keeps the old content."""
        target = self.root / "project.md"
        before = target.read_text()
        with mock.patch("sql_rag_util.atomic.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                atomic_write_text(target, "new")
        self.assertEqual(target.read_text(), before)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
