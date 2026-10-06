"""Tests for the sdist, the editable wheel, and the command line of the build backend."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

import sql_rag_util
from tests.distribution.support import ROOT, backend, inside

BASE = f"sql_rag_util-{sql_rag_util.__version__}"


class DistributionTest(unittest.TestCase):
    """The sdist rebuilds the same wheel, the editable wheel exposes the package alone, and the CLI builds both."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = pathlib.Path(tmp.name)
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("SOURCE_DATE_EPOCH", None)

    def _sdist(self, directory: str = "sdist") -> pathlib.Path:
        return self.out / directory / inside(ROOT, backend().build_sdist, str(self.out / directory))

    def test_sdist_members(self) -> None:
        """One top directory, PKG-INFO equal to METADATA, fixed owners, modes, and times, and no stray files."""
        sdist = self._sdist()
        self.assertEqual(sdist.name, f"{BASE}.tar.gz")
        self.assertEqual(int.from_bytes(sdist.read_bytes()[4:8], "little"), backend().ZIP_EPOCH)
        with tarfile.open(sdist) as archive:
            members = archive.getmembers()
            pkg_info = archive.extractfile(f"{BASE}/PKG-INFO")
            assert pkg_info is not None
            self.assertEqual(pkg_info.read().decode(), backend().metadata_text(backend().load_project(ROOT)))
        names = [m.name for m in members]
        self.assertEqual(names, sorted(names))
        self.assertTrue(all(n.startswith(f"{BASE}/") for n in names))
        self.assertEqual({(m.uid, m.gid, m.uname, m.gname, m.mode, m.mtime, m.type) for m in members}, {(0, 0, "", "", 0o644, backend().ZIP_EPOCH, tarfile.REGTYPE)})
        self.assertFalse([n for n in names if "__pycache__" in n or "/." in n])
        if shutil.which("git") and (ROOT / ".git").exists():
            listed = subprocess.run(["git", "ls-files", *backend().SDIST_FILES, *backend().SDIST_DIRS], capture_output=True, text=True, cwd=ROOT, check=True).stdout.split()
            self.assertEqual(sorted(n.removeprefix(f"{BASE}/") for n in names if not n.endswith("/PKG-INFO")), sorted(listed))

    def test_sdist_is_reproducible_and_rebuilds_the_same_wheel(self) -> None:
        """Two sdists are identical, and the wheel built from an unpacked sdist equals the repository's."""
        sdist = self._sdist("a")
        self.assertEqual(sdist.read_bytes(), self._sdist("b").read_bytes())
        with tarfile.open(sdist) as archive:
            archive.extractall(self.out / "unpacked", filter="data")
        from_sdist = inside(self.out / "unpacked" / BASE, backend().build_wheel, str(self.out / "from-sdist"))
        from_repository = inside(ROOT, backend().build_wheel, str(self.out / "from-repository"))
        self.assertEqual((self.out / "from-sdist" / from_sdist).read_bytes(), (self.out / "from-repository" / from_repository).read_bytes())

    def test_editable_wheel_exposes_only_the_package(self) -> None:
        """Installed into a bare site directory, the editable wheel imports the source tree and nothing beside it."""
        wheel = self.out / inside(ROOT, backend().build_editable, str(self.out))
        site = self.out / "site"
        with zipfile.ZipFile(wheel) as archive:
            self.assertEqual(sorted(n for n in archive.namelist() if "/" not in n), ["__editable__.sql_rag_util.pth", "__editable___sql_rag_util_finder.py"])
            archive.extractall(site)
        code = "import importlib.util, site, sys; site.addsitedir(sys.argv[1]); import sql_rag_util; print(sql_rag_util.__file__); print(importlib.util.find_spec('tests'))"
        completed = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(site)], capture_output=True, text=True, cwd=self.out, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.splitlines(), [str(ROOT.resolve() / "sql_rag_util" / "__init__.py"), "None"])

    def test_command_line(self) -> None:
        """The script builds the wheel and the sdist and prints both paths; a build error is one line on stderr."""
        script = ROOT / "buildsys" / "sql_rag_util_build.py"
        built = subprocess.run([sys.executable, str(script), "--outdir", str(self.out / "dist")], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual([pathlib.Path(line).name for line in built.stdout.splitlines()], [f"{BASE}-py3-none-any.whl", f"{BASE}.tar.gz"])
        only = subprocess.run([sys.executable, str(script), "--sdist", "--outdir", str(self.out / "only")], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual([p.name for p in (self.out / "only").iterdir()], [f"{BASE}.tar.gz"], only.stderr)
        failed = subprocess.run([sys.executable, str(script), "--outdir", str(self.out / "x")], capture_output=True, text=True, timeout=60, check=False, env={**os.environ, "SOURCE_DATE_EPOCH": "soon"})
        self.assertEqual((failed.returncode, failed.stderr), (1, "error: SOURCE_DATE_EPOCH must be whole seconds; got 'soon'\n"))


if __name__ == "__main__":
    unittest.main()
