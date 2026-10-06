"""A standard-library build backend for sql_rag_util, implementing PEP 517 and PEP 660.

Once ``pyproject.toml`` names this module with ``requires = []``, ``pip install``
builds the package without downloading anything. The backend reads only the
``[project]`` keys this project uses and refuses any other, so a metadata
change it does not understand fails the build instead of being dropped.
See ``docs/design/in-tree-build-backend.md``.
"""

from __future__ import annotations

import ast
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "BuildError",
    "Project",
    "load_project",
    "metadata_text",
]

PACKAGE = "sql_rag_util"
METADATA_VERSION = "2.4"
SUPPORTED_KEYS = frozenset(
    {"name", "version", "description", "readme", "requires-python", "license", "license-files", "authors", "keywords", "classifiers", "urls", "dependencies"}
)
_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_GLOB = frozenset("*?[]")
_MAX_URL_LABEL = 32


class BuildError(Exception):
    """The project cannot be built as declared."""


@dataclass(frozen=True, slots=True)
class Project:
    """The ``[project]`` table, validated, with the README text it points to.

    Parameters
    ----------
    name
        Distribution name as declared.
    version
        ``MAJOR.MINOR.PATCH``, equal to the package's ``__version__``.
    summary
        The one-line description.
    readme
        The README's Markdown text.
    requires_python
        The supported Python versions.
    license
        An SPDX license expression.
    license_files
        License file paths relative to the project root.
    authors
        Author names.
    keywords
        Search keywords.
    classifiers
        Trove classifiers.
    urls
        ``(label, url)`` pairs.
    """

    name: str
    version: str
    summary: str
    readme: str
    requires_python: str
    license: str
    license_files: tuple[str, ...]
    authors: tuple[str, ...]
    keywords: tuple[str, ...]
    classifiers: tuple[str, ...]
    urls: tuple[tuple[str, str], ...]

    @property
    def distribution(self) -> str:
        """Return the name as it appears in file names: lowercase, runs of ``-_.`` as one underscore."""
        return re.sub(r"[-_.]+", "_", self.name).lower()

    @property
    def dist_info(self) -> str:
        """Return the name of the ``.dist-info`` directory."""
        return f"{self.distribution}-{self.version}.dist-info"


def _line(value: object, key: str) -> str:
    if not isinstance(value, str) or not value or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in value):
        raise BuildError(f"[project] {key} must be a non-empty single-line string")
    return value


def _lines(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise BuildError(f"[project] {key} must be a list of strings")
    return tuple(_line(v, key) for v in value)


def _package_version(root: Path) -> str:
    tree = ast.parse((root / PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise BuildError(f"{PACKAGE}/__init__.py assigns no string __version__")


def _license_files(root: Path, value: object) -> tuple[str, ...]:
    files = _lines(value, "license-files")
    for name in files:
        path = (root / name).resolve()
        if _GLOB & set(name) or not path.is_relative_to(root.resolve()) or not path.is_file():
            raise BuildError(f"[project] license-files entry {name!r} must name a file inside the project, without glob characters")
    return files


def _authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(a, dict) and set(a) == {"name"} for a in value):
        raise BuildError("[project] authors must be a list of tables with a name only")
    return tuple(_line(a["name"], "authors") for a in value)


def _urls(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        raise BuildError("[project.urls] must be a table")
    for label, url in value.items():
        if len(_line(label, "urls")) > _MAX_URL_LABEL or not _line(url, "urls").startswith("https://"):
            raise BuildError(f"[project.urls] {label!r} needs a label of at most {_MAX_URL_LABEL} characters and an https URL")
    return tuple(value.items())


def load_project(root: Path) -> Project:
    """Read and validate ``root/pyproject.toml``.

    Raises
    ------
    BuildError
        On any key the backend does not support, a dependency, a value of the
        wrong shape, a license file outside the project, or a version that
        differs from the package's ``__version__``.
    """
    try:
        table = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise BuildError(f"cannot read [project] from pyproject.toml: {exc}") from exc
    unsupported = sorted(set(table) - SUPPORTED_KEYS)
    if unsupported:
        raise BuildError(f"[project] keys this backend does not support: {', '.join(unsupported)}")
    if table.get("dependencies", []) != []:
        raise BuildError("[project] dependencies must be empty; the package depends on nothing")
    name, version = _line(table.get("name"), "name"), _line(table.get("version"), "version")
    if not _NAME.match(name) or not _VERSION.match(version):
        raise BuildError(f"[project] name {name!r} must be a valid distribution name and version {version!r} MAJOR.MINOR.PATCH")
    if version != _package_version(root):
        raise BuildError(f"[project] version {version} differs from {PACKAGE}.__version__ {_package_version(root)}")
    readme = _line(table.get("readme"), "readme")
    if not readme.endswith(".md") or not (root / readme).is_file():
        raise BuildError("[project] readme must name a Markdown file in the project")
    return Project(
        name,
        version,
        _line(table.get("description"), "description"),
        (root / readme).read_text(encoding="utf-8"),
        _line(table.get("requires-python"), "requires-python"),
        _line(table.get("license"), "license"),
        _license_files(root, table.get("license-files")),
        _authors(table.get("authors")),
        _lines(table.get("keywords", []), "keywords"),
        _lines(table.get("classifiers", []), "classifiers"),
        _urls(table.get("urls", {})),
    )


def metadata_text(project: Project) -> str:
    """Return the core metadata file, version 2.4, with the README as its body."""
    lines = [f"Metadata-Version: {METADATA_VERSION}", f"Name: {project.name}", f"Version: {project.version}", f"Summary: {project.summary}"]
    if project.keywords:
        lines.append(f"Keywords: {','.join(project.keywords)}")
    lines += [f"Author: {', '.join(project.authors)}", f"License-Expression: {project.license}"]
    lines += [f"License-File: {name}" for name in project.license_files]
    lines += [f"Classifier: {c}" for c in project.classifiers]
    lines.append(f"Requires-Python: {project.requires_python}")
    lines += [f"Project-URL: {label}, {url}" for label, url in project.urls]
    lines.append("Description-Content-Type: text/markdown")
    return "\n".join(lines) + "\n\n" + project.readme
