"""The CI rules, checked over every GitHub Actions workflow in the repository."""

from __future__ import annotations

import pathlib
import re
import unittest

WORKFLOWS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"
_USES = re.compile(r"^\s*(?:-\s*)?uses\s*:")
_RUN = re.compile(r"^(\s*)(?:-\s*)?run:\s*(.*)$")
_EXPRESSION = "${{"


def _run_scripts(lines: list[str]) -> list[tuple[int, str]]:
    scripts: list[tuple[int, str]] = []
    block_indent: int | None = None
    for number, line in enumerate(lines, start=1):
        if block_indent is not None:
            if line.strip() and len(line) - len(line.lstrip()) <= block_indent:
                block_indent = None
            else:
                scripts.append((number, line))
                continue
        match = _RUN.match(line)
        if match:
            inline = match.group(2).strip()
            if inline in ("|", ">", "|-", ">-"):
                block_indent = len(match.group(1))
            else:
                scripts.append((number, inline))
    return scripts


class WorkflowTest(unittest.TestCase):
    """No external actions, no privileged triggers, least permissions, and no expressions inside scripts."""

    def setUp(self) -> None:
        if not WORKFLOWS.is_dir():
            self.skipTest("no .github/workflows here, as in an unpacked sdist")
        self.files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
        self.assertTrue(self.files)

    def test_no_external_actions_or_privileged_triggers(self) -> None:
        """No uses: key at all, and none of pull_request_target, workflow_run, or secrets."""
        for path in self.files:
            lines = path.read_text(encoding="utf-8").splitlines()
            with self.subTest(workflow=path.name):
                self.assertEqual([n for n, line in enumerate(lines, start=1) if _USES.match(line)], [])
                text = "\n".join(lines)
                for forbidden in ("pull_request_target", "workflow_run", "secrets."):
                    self.assertNotIn(forbidden, text)

    def test_least_privilege_and_bounded_jobs(self) -> None:
        """Permissions start empty, jobs grant read only, runners are pinned, and every job has a timeout."""
        for path in self.files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertIn("\npermissions: {}\n", text)
                self.assertEqual(re.findall(r"^\s+permissions:\s*\n\s+(\S.*)$", text, re.M), ["contents: read"] * text.count("runs-on:"))
                self.assertEqual(text.count("runs-on:"), len(re.findall(r"runs-on: ubuntu-\d+\.\d+$", text, re.M)))
                self.assertEqual(text.count("runs-on:"), text.count("timeout-minutes:"))

    def test_scripts_take_values_only_from_the_environment(self) -> None:
        """No ${{ }} expression appears inside a run script, so no event value can become shell code."""
        for path in self.files:
            with self.subTest(workflow=path.name):
                scripts = _run_scripts(path.read_text(encoding="utf-8").splitlines())
                self.assertTrue(scripts)
                self.assertEqual([n for n, line in scripts if _EXPRESSION in line], [])


if __name__ == "__main__":
    unittest.main()
