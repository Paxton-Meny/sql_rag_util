"""Load the build backend by path and make throwaway copies of the project to build."""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest
from types import ModuleType

__all__ = ["ROOT", "backend", "project_copy"]

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_MODULE = "sql_rag_util_build"


def backend() -> ModuleType:
    """Return the backend module, loaded from ``buildsys/`` without touching ``sys.path``."""
    if _MODULE not in sys.modules:
        spec = importlib.util.spec_from_file_location(_MODULE, ROOT / "buildsys" / f"{_MODULE}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[_MODULE] = module
        spec.loader.exec_module(module)
    return sys.modules[_MODULE]


def project_copy(test: unittest.TestCase, *, pyproject: str | None = None) -> pathlib.Path:
    """Return a copy of the files a build reads, removed when ``test`` ends, optionally with another pyproject.toml."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = pathlib.Path(tmp.name) / "project"
    shutil.copytree(ROOT / "sql_rag_util", root / "sql_rag_util", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, root / name)
    if pyproject is not None:
        (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return root
