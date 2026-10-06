"""Tests for the wheels the build backend writes."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

import sql_rag_util
from tests.distribution.support import ROOT, backend, inside, project_copy

DIST_INFO = f"sql_rag_util-{sql_rag_util.__version__}.dist-info"
_IMPORT_CHECK = """
import pkgutil, sqlite3, sys
import sql_rag_util
assert sql_rag_util.__file__.startswith(sys.argv[1]), sql_rag_util.__file__
for module in pkgutil.walk_packages(sql_rag_util.__path__, "sql_rag_util."):
    __import__(module.name)
engine = sql_rag_util.SqlRag(sqlite3.connect(":memory:"))
print(engine.dispatch("list_tables", {})["tables"])
"""


class WheelTest(unittest.TestCase):
    """The wheel holds exactly the package and its dist-info, verifiably, reproducibly, and importably."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = pathlib.Path(tmp.name)
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("SOURCE_DATE_EPOCH", None)

    def _build(self, root: pathlib.Path = ROOT, directory: str = "a", metadata: str | None = None) -> pathlib.Path:
        return self.out / directory / inside(root, backend().build_wheel, str(self.out / directory), None, metadata)

    def test_contents_and_record(self) -> None:
        """Every package module and py.typed, then METADATA, WHEEL, the license, and RECORD last, each hash verified."""
        wheel = self._build()
        self.assertEqual(wheel.name, f"sql_rag_util-{sql_rag_util.__version__}-py3-none-any.whl")
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            record = list(csv.reader(io.StringIO(archive.read(f"{DIST_INFO}/RECORD").decode())))
            for name, digest, size in record[:-1]:
                with self.subTest(entry=name):
                    data = archive.read(name)
                    self.assertEqual(digest, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode())
                    self.assertEqual(int(size), len(data))
            infos = archive.infolist()
        package = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "sql_rag_util").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        self.assertEqual(names[: len(package)], package)
        self.assertEqual(names[len(package):], [f"{DIST_INFO}/{n}" for n in ("METADATA", "WHEEL", "licenses/LICENSE", "RECORD")])
        self.assertEqual([r[0] for r in record], names)
        self.assertEqual(record[-1], [f"{DIST_INFO}/RECORD", "", ""])
        self.assertIn("sql_rag_util/py.typed", names)
        self.assertEqual({(i.date_time, stat.S_IMODE(i.external_attr >> 16)) for i in infos}, {((1980, 1, 1, 0, 0, 0), 0o644)})

    def test_reproducible_and_dated_by_source_date_epoch(self) -> None:
        """Two builds are identical; SOURCE_DATE_EPOCH sets every timestamp; a non-number is refused."""
        self.assertEqual(self._build(directory="a").read_bytes(), self._build(directory="b").read_bytes())
        os.environ["SOURCE_DATE_EPOCH"] = "1700000000"
        with zipfile.ZipFile(self._build(directory="c")) as archive:
            self.assertEqual({i.date_time for i in archive.infolist()}, {time.gmtime(1700000000)[:6]})
        os.environ["SOURCE_DATE_EPOCH"] = "soon"
        with self.assertRaises(backend().BuildError):
            self._build(directory="d")

    def test_prepared_metadata_must_match(self) -> None:
        """A build given prepared metadata accepts its own and refuses anything else."""
        prepared = self.out / "prepared"
        prepared.mkdir()
        inside(ROOT, backend().prepare_metadata_for_build_wheel, str(prepared))
        self._build(directory="a", metadata=str(prepared))
        (prepared / DIST_INFO / "METADATA").write_text("Metadata-Version: 2.4\nName: other\n", encoding="utf-8")
        with self.assertRaises(backend().BuildError):
            self._build(directory="b", metadata=str(prepared))

    def test_stray_files_and_symlinks_fail_the_build(self) -> None:
        """Only .py files and py.typed ship; anything else in the package stops the build."""
        for stray in ("notes.txt", "link.py"):
            with self.subTest(stray=stray):
                root = project_copy(self)
                path = root / "sql_rag_util" / stray
                if stray == "link.py":
                    path.symlink_to(root / "sql_rag_util" / "atomic.py")
                else:
                    path.write_text("x")
                with self.assertRaises(backend().BuildError):
                    self._build(root, directory=stray)

    def test_extracted_wheel_imports_on_its_own(self) -> None:
        """With only the unpacked wheel on the path and site disabled, every module imports and an engine works."""
        target = self.out / "site"
        with zipfile.ZipFile(self._build()) as archive:
            archive.extractall(target)
        code = f"import sys; sys.path.insert(0, sys.argv[1]); exec({_IMPORT_CHECK!r})"
        completed = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(target)], capture_output=True, text=True, cwd=self.out, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "[]\n")


if __name__ == "__main__":
    unittest.main()
