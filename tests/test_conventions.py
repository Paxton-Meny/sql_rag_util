"""The written conventions, checked over every Python file in the repository."""

from __future__ import annotations

import ast
import functools
import io
import pathlib
import sys
import tokenize
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_DIRS = ("sql_rag_util", "benchmarks", "buildsys")
FIRST_PARTY = frozenset({"sql_rag_util", "tests", "benchmarks"})


def _files(*dirs: str) -> list[pathlib.Path]:
    return sorted(p for d in dirs if (ROOT / d).is_dir() for p in (ROOT / d).rglob("*.py"))


@functools.cache
def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _where(path: pathlib.Path, node: ast.AST | None = None) -> str:
    line = f":{getattr(node, 'lineno', 0)}" if node is not None else ""
    return f"{path.relative_to(ROOT)}{line}"


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _public(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    out: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []
    pending: list[ast.AST] = [tree]
    while pending:
        scope = pending.pop()
        for child in ast.iter_child_nodes(scope):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not child.name.startswith("_"):
                out.append(child)
                if isinstance(child, ast.ClassDef):
                    pending.append(child)
    return out


class ConventionsTest(unittest.TestCase):
    """No comments, future annotations first, explicit exports, full annotations, docstrings, stdlib imports."""

    def test_no_comments(self) -> None:
        """Explanation lives in docstrings and docs, so no file contains a comment token."""
        found = []
        for path in _files(*SOURCE_DIRS, "tests"):
            tokens = tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline)
            found += [f"{_where(path)}:{t.start[0]}" for t in tokens if t.type == tokenize.COMMENT]
        self.assertEqual(found, [])

    def test_future_annotations_come_first(self) -> None:
        """Every module with code starts, after its docstring, with the annotations future import."""
        found = []
        for path in _files(*SOURCE_DIRS, "tests"):
            tree = _tree(path)
            code = tree.body[1:] if ast.get_docstring(tree) else tree.body
            first = code[0] if code else None
            if first is not None and not (isinstance(first, ast.ImportFrom) and first.module == "__future__" and first.names[0].name == "annotations"):
                found.append(_where(path))
        self.assertEqual(found, [])

    def test_modules_declare_what_they_export(self) -> None:
        """A source module defining public names lists them in __all__, and every listed name exists."""
        found = []
        for path in _files(*SOURCE_DIRS):
            tree = _tree(path)
            bound = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)) for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
            bound |= {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            bound |= {(a.asname or a.name).split(".")[0] for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            exported = next((n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)), None)
            defines_public = any(not n.name.startswith("_") for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            if exported is None:
                if defines_public:
                    found.append(f"{_where(path)}: no __all__")
                continue
            names = ast.literal_eval(exported)
            found += [f"{_where(path)}: {name} is not defined" for name in names if name not in bound | {"__version__"}]
        self.assertEqual(found, [])

    def test_every_signature_is_annotated(self) -> None:
        """Every parameter other than self and cls, and every return, carries an annotation."""
        found = []
        for path in _files(*SOURCE_DIRS, "tests"):
            for node in _functions(_tree(path)):
                arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs + [a for a in (node.args.vararg, node.args.kwarg) if a is not None]
                missing = [a.arg for a in arguments if a.annotation is None and a.arg not in ("self", "cls")]
                if missing or node.returns is None:
                    found.append(f"{_where(path, node)} {node.name}")
        self.assertEqual(found, [])

    def test_public_surfaces_have_docstrings(self) -> None:
        """Modules, public classes, functions, and methods are documented; so are test classes and test methods."""
        found = []
        for path in _files(*SOURCE_DIRS):
            tree = _tree(path)
            if not ast.get_docstring(tree):
                found.append(_where(path))
            found += [f"{_where(path, n)} {n.name}" for n in _public(tree) if not ast.get_docstring(n)]
        for path in _files("tests"):
            tree = _tree(path)
            if not ast.get_docstring(tree):
                found.append(_where(path))
            tests = [n for n in _public(tree) if n.name.startswith("test_") or (isinstance(n, ast.ClassDef) and n.name.endswith("Test"))]
            found += [f"{_where(path, n)} {n.name}" for n in tests if not ast.get_docstring(n)]
        self.assertEqual(found, [])

    def test_imports_are_standard_library_or_first_party(self) -> None:
        """Nothing outside the standard library is imported anywhere, including under TYPE_CHECKING and inside functions."""
        found = []
        for path in _files(*SOURCE_DIRS, "tests"):
            for node in ast.walk(_tree(path)):
                if isinstance(node, ast.ImportFrom) and node.level:
                    found.append(f"{_where(path, node)} relative import")
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else []
                found += [f"{_where(path, node)} {n}" for n in names if n.split(".")[0] not in sys.stdlib_module_names | FIRST_PARTY]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
