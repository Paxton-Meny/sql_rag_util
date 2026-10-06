"""Tests for how the build backend reads pyproject.toml and writes core metadata."""

from __future__ import annotations

import email.parser
import email.policy
import pathlib
import tempfile
import unittest

import sql_rag_util
from tests.distribution.support import ROOT, backend, inside, project_copy

PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


class LoadProjectTest(unittest.TestCase):
    """The real pyproject.toml loads, and every shape the backend does not support is refused."""

    def test_the_project_loads(self) -> None:
        """Name, version, license, and the README come through unchanged."""
        project = backend().load_project(ROOT)
        self.assertEqual((project.name, project.version, project.distribution), ("sql_rag_util", sql_rag_util.__version__, "sql_rag_util"))
        self.assertEqual((project.license, project.license_files), ("PolyForm-Noncommercial-1.0.0", ("LICENSE",)))
        self.assertEqual(project.readme, (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertEqual(project.dist_info, f"sql_rag_util-{sql_rag_util.__version__}.dist-info")

    def test_unsupported_declarations_fail_the_build(self) -> None:
        """Each change below would silently ship wrong metadata if it were ignored, so each is an error."""
        version = f'version = "{sql_rag_util.__version__}"'
        cases = {
            "dynamic": PYPROJECT.replace(version, 'dynamic = ["version"]'),
            "a dependency": PYPROJECT.replace("dependencies = []", 'dependencies = ["requests"]'),
            "optional dependencies": PYPROJECT + '\n[project.optional-dependencies]\nfast = ["orjson"]\n',
            "scripts": PYPROJECT + '\n[project.scripts]\nsqlrag = "sql_rag_util.mcp:main"\n',
            "an unknown key": PYPROJECT.replace("dependencies = []", "dependencies = []\nmaintainers = []"),
            "a license table": PYPROJECT.replace('license = "PolyForm-Noncommercial-1.0.0"', 'license = { file = "LICENSE" }'),
            "a license glob": PYPROJECT.replace('license-files = ["LICENSE"]', 'license-files = ["LICEN*"]'),
            "a license outside": PYPROJECT.replace('license-files = ["LICENSE"]', 'license-files = ["../LICENSE"]'),
            "a missing license": PYPROJECT.replace('license-files = ["LICENSE"]', 'license-files = ["COPYING"]'),
            "a reStructuredText readme": PYPROJECT.replace('readme = "README.md"', 'readme = "README.rst"'),
            "a newline in the summary": PYPROJECT.replace('description = "', 'description = "Line\\nInjected: header '),
            "a bad name": PYPROJECT.replace('name = "sql_rag_util"', 'name = "-sql"'),
            "a short version": PYPROJECT.replace(version, 'version = "0.1"'),
            "a mismatched version": PYPROJECT.replace(version, 'version = "9.9.9"'),
            "an author email": PYPROJECT.replace('{ name = "Paxton-Meny" }', '{ name = "Paxton-Meny", email = "x@example.com" }'),
            "a long url label": PYPROJECT.replace("Issues =", "Issues-and-other-things-about-the-project =", 1),
            "a plain http url": PYPROJECT.replace('Issues = "https://', 'Issues = "http://'),
        }
        for case, text in cases.items():
            with self.subTest(case=case):
                self.assertNotEqual(text, PYPROJECT)
                with self.assertRaises(backend().BuildError):
                    backend().load_project(project_copy(self, pyproject=text))


class MetadataTest(unittest.TestCase):
    """METADATA parses as an email message carrying every field, and the hooks behave as PEP 517 asks."""

    def test_metadata_fields(self) -> None:
        """Every declared value appears once in its field, and the README is the body."""
        project = backend().load_project(ROOT)
        message = email.parser.Parser(policy=email.policy.compat32).parsestr(backend().metadata_text(project))
        self.assertEqual(message["Metadata-Version"], "2.4")
        self.assertEqual((message["Name"], message["Version"], message["Summary"]), (project.name, project.version, project.summary))
        self.assertEqual((message["License-Expression"], message.get_all("License-File")), ("PolyForm-Noncommercial-1.0.0", ["LICENSE"]))
        self.assertEqual(message.get_all("Classifier"), list(project.classifiers))
        self.assertEqual(message.get_all("Project-URL"), [f"{label}, {url}" for label, url in project.urls])
        self.assertEqual((message["Requires-Python"], message["Author"]), (">=3.11", "Paxton-Meny"))
        self.assertEqual(message["Keywords"], ",".join(project.keywords))
        self.assertEqual(message["Description-Content-Type"], "text/markdown")
        self.assertEqual(message.get_payload(), project.readme)


    def test_hooks(self) -> None:
        """No hook asks for build requirements, settings are refused, and prepare_metadata writes the dist-info."""
        module = backend()
        for hook in (module.get_requires_for_build_wheel, module.get_requires_for_build_sdist, module.get_requires_for_build_editable):
            with self.subTest(hook=hook.__name__):
                self.assertEqual(hook(None), [])
                self.assertEqual(hook({}), [])
                with self.assertRaises(module.BuildError):
                    hook({"key": "value"})
        with tempfile.TemporaryDirectory() as tmp:
            for hook in (module.prepare_metadata_for_build_wheel, module.prepare_metadata_for_build_editable):
                with self.subTest(hook=hook.__name__):
                    out = pathlib.Path(tmp) / hook.__name__
                    out.mkdir()
                    name = inside(ROOT, hook, str(out))
                    files = sorted(p.relative_to(out / name).as_posix() for p in (out / name).rglob("*") if p.is_file())
                    self.assertEqual(files, ["METADATA", "WHEEL", "licenses/LICENSE"])
                    self.assertEqual((out / name / "licenses" / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
                    self.assertIn("Tag: py3-none-any", (out / name / "WHEEL").read_text(encoding="utf-8"))



if __name__ == "__main__":
    unittest.main()
