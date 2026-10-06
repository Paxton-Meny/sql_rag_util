"""A standard-library build backend for sql_rag_util, implementing PEP 517 and PEP 660.

Once ``pyproject.toml`` names this module with ``requires = []``, ``pip install``
builds the package without downloading anything. The backend reads only the
``[project]`` keys this project uses and refuses any other, so a metadata
change it does not understand fails the build instead of being dropped.
See ``docs/design/in-tree-build-backend.md``.
"""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import gzip
import hashlib
import io
import os
import re
import stat
import sys
import tarfile
import time
import tomllib
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "BuildError",
    "Project",
    "load_project",
    "metadata_text",
    "wheel_text",
    "write_dist_info",
    "source_date_epoch",
    "get_requires_for_build_wheel",
    "get_requires_for_build_sdist",
    "get_requires_for_build_editable",
    "prepare_metadata_for_build_wheel",
    "prepare_metadata_for_build_editable",
    "write_wheel",
    "build_wheel",
    "build_sdist",
    "build_editable",
    "main",
]

PACKAGE = "sql_rag_util"
METADATA_VERSION = "2.4"
TAG = "py3-none-any"
PACKAGE_SUFFIXES = frozenset({".py", ".typed"})
SDIST_FILES = ("pyproject.toml", "README.md", "LICENSE", "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md")
SDIST_DIRS = ("buildsys", PACKAGE, "docs", "tests", "benchmarks")
SDIST_SUFFIXES = frozenset({".py", ".md", ".typed"})
ZIP_EPOCH = 315532800
FILE_MODE = 0o644
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


def wheel_text(project: Project) -> str:
    """Return the ``WHEEL`` file for a pure-Python wheel."""
    return f"Wheel-Version: 1.0\nGenerator: sql_rag_util_build {project.version}\nRoot-Is-Purelib: true\nTag: {TAG}\n"


def _check_settings(config_settings: dict[str, Any] | None) -> None:
    if config_settings:
        raise BuildError(f"this backend takes no config settings; got {sorted(config_settings)}")


def get_requires_for_build_wheel(config_settings: dict[str, Any] | None = None) -> list[str]:
    """Return the extra build requirements for a wheel: none."""
    _check_settings(config_settings)
    return []


def get_requires_for_build_sdist(config_settings: dict[str, Any] | None = None) -> list[str]:
    """Return the extra build requirements for an sdist: none."""
    _check_settings(config_settings)
    return []


def get_requires_for_build_editable(config_settings: dict[str, Any] | None = None) -> list[str]:
    """Return the extra build requirements for an editable wheel: none."""
    _check_settings(config_settings)
    return []


def write_dist_info(project: Project, root: Path, directory: Path) -> Path:
    """Write ``METADATA``, ``WHEEL``, and the license files into ``directory/<dist-info>`` and return that path."""
    dist_info = directory / project.dist_info
    (dist_info / "licenses").mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(metadata_text(project), encoding="utf-8", newline="\n")
    (dist_info / "WHEEL").write_text(wheel_text(project), encoding="utf-8", newline="\n")
    for name in project.license_files:
        target = dist_info / "licenses" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())
    return dist_info


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings: dict[str, Any] | None = None) -> str:
    """Write the wheel's ``.dist-info`` directory into ``metadata_directory`` and return its name."""
    _check_settings(config_settings)
    root = Path.cwd()
    return write_dist_info(load_project(root), root, Path(metadata_directory)).name


def prepare_metadata_for_build_editable(metadata_directory: str, config_settings: dict[str, Any] | None = None) -> str:
    """Write the editable wheel's ``.dist-info`` directory, which is the same, and return its name."""
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def source_date_epoch() -> int:
    """Return the archive timestamp: ``SOURCE_DATE_EPOCH`` when set, never before 1980, which zip cannot store.

    Raises
    ------
    BuildError
        When ``SOURCE_DATE_EPOCH`` is set to something other than whole seconds.
    """
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return ZIP_EPOCH
    if not raw.isdigit():
        raise BuildError(f"SOURCE_DATE_EPOCH must be whole seconds; got {raw!r}")
    return max(int(raw), ZIP_EPOCH)


def _files(root: Path, top: str, suffixes: frozenset[str]) -> list[tuple[str, bytes]]:
    files = []
    for directory, subdirectories, names in os.walk(root / top):
        subdirectories[:] = sorted(d for d in subdirectories if d != "__pycache__" and not d.startswith("."))
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or path.suffix not in suffixes:
                raise BuildError(f"{relative} is not a regular {', '.join(sorted(suffixes))} file; remove it or teach the backend about it")
            files.append((relative, path.read_bytes()))
    return files


def _record(entries: list[tuple[str, bytes]], record: str) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for name, data in entries:
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow((name, f"sha256={digest}", len(data)))
    writer.writerow((record, "", ""))
    return out.getvalue().encode()


def _write_zip(target: Path, entries: list[tuple[str, bytes]]) -> None:
    moment = time.gmtime(source_date_epoch())[:6]
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for name, data in entries:
                info = zipfile.ZipInfo(name, moment)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | FILE_MODE) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data, compresslevel=9)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_wheel(project: Project, root: Path, directory: Path, files: list[tuple[str, bytes]]) -> str:
    """Write a wheel of ``files`` plus the dist-info and ``RECORD`` into ``directory`` and return its file name."""
    dist_info = project.dist_info
    entries = sorted(files)
    entries += [(f"{dist_info}/METADATA", metadata_text(project).encode()), (f"{dist_info}/WHEEL", wheel_text(project).encode())]
    entries += [(f"{dist_info}/licenses/{name}", (root / name).read_bytes()) for name in project.license_files]
    entries.append((f"{dist_info}/RECORD", _record(entries, f"{dist_info}/RECORD")))
    name = f"{project.distribution}-{project.version}-{TAG}.whl"
    directory.mkdir(parents=True, exist_ok=True)
    _write_zip(directory / name, entries)
    return name


def build_wheel(wheel_directory: str, config_settings: dict[str, Any] | None = None, metadata_directory: str | None = None) -> str:
    """Build the wheel into ``wheel_directory`` and return its file name.

    Raises
    ------
    BuildError
        When ``metadata_directory`` holds metadata other than what this build
        writes, since PEP 517 requires the two to match.
    """
    _check_settings(config_settings)
    root = Path.cwd()
    project = _prepared(load_project(root), metadata_directory)
    return write_wheel(project, root, Path(wheel_directory), _files(root, PACKAGE, PACKAGE_SUFFIXES))


def _prepared(project: Project, metadata_directory: str | None) -> Project:
    if metadata_directory is not None:
        prepared = Path(metadata_directory) / project.dist_info / "METADATA"
        if not prepared.is_file() or prepared.read_text(encoding="utf-8") != metadata_text(project):
            raise BuildError(f"{prepared} does not match the metadata this build writes")
    return project


_FINDER = """\"\"\"Import {package} from its source tree for an editable install, and expose nothing else there.\"\"\"

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys

__all__ = ["install"]

_PACKAGE = {package!r}
_LOCATION = {location!r}


class _Finder:
    \"\"\"Find the editable package; every other import is left to the normal finders.\"\"\"

    @classmethod
    def find_spec(cls, fullname: str, path: object = None, target: object = None) -> importlib.machinery.ModuleSpec | None:
        \"\"\"Return the package's spec from the source tree, or None for any other name.\"\"\"
        if fullname != _PACKAGE:
            return None
        return importlib.util.spec_from_file_location(fullname, os.path.join(_LOCATION, "__init__.py"), submodule_search_locations=[_LOCATION])


def install() -> None:
    \"\"\"Add the finder to the import system once.\"\"\"
    if _Finder not in sys.meta_path:
        sys.meta_path.append(_Finder)
"""


def build_editable(wheel_directory: str, config_settings: dict[str, Any] | None = None, metadata_directory: str | None = None) -> str:
    """Build a PEP 660 editable wheel that imports the package from this source tree, and return its file name.

    The wheel holds a ``.pth`` file that installs an import finder for the
    package alone, so ``tests`` and ``benchmarks`` beside it never become
    importable in the target environment.
    """
    _check_settings(config_settings)
    root = Path.cwd()
    project = _prepared(load_project(root), metadata_directory)
    module = f"__editable___{project.distribution}_finder"
    finder = _FINDER.format(package=PACKAGE, location=str((root / PACKAGE).resolve()))
    files = [(f"{module}.py", finder.encode()), (f"__editable__.{project.distribution}.pth", f"import {module}; {module}.install()\n".encode())]
    return write_wheel(project, root, Path(wheel_directory), files)


def _write_tar(target: Path, members: list[tuple[str, bytes]]) -> None:
    epoch = source_date_epoch()
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in members:
                    info = tarfile.TarInfo(name)
                    info.size, info.mtime, info.mode = len(data), epoch, FILE_MODE
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def build_sdist(sdist_directory: str, config_settings: dict[str, Any] | None = None) -> str:
    """Build the source distribution into ``sdist_directory`` and return its file name.

    It holds ``PKG-INFO``, the project files, the backend, the package, the
    docs, the tests, and the benchmark, so the gate can run inside it and a
    wheel built from it is identical to one built from the repository.
    """
    _check_settings(config_settings)
    root = Path.cwd()
    project = load_project(root)
    base = f"{project.distribution}-{project.version}"
    members = [("PKG-INFO", metadata_text(project).encode())] + [(name, (root / name).read_bytes()) for name in SDIST_FILES]
    for top in SDIST_DIRS:
        members += _files(root, top, SDIST_SUFFIXES)
    target = Path(sdist_directory) / f"{base}.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_tar(target, [(f"{base}/{name}", data) for name, data in sorted(members)])
    return target.name


def main(argv: list[str] | None = None) -> int:
    """Build the wheel and the sdist of this repository into ``dist/``, or ``--outdir``, and print their paths."""
    parser = argparse.ArgumentParser(prog="python3 buildsys/sql_rag_util_build.py", description="Build sql_rag_util with the standard library only.")
    parser.add_argument("--outdir", type=Path, default=None, help="output directory (default: dist/ in the repository)")
    parser.add_argument("--wheel", action="store_true", help="build only the wheel")
    parser.add_argument("--sdist", action="store_true", help="build only the sdist")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    outdir = (args.outdir or root / "dist").resolve()
    builders = [b for b, chosen in ((build_wheel, args.wheel), (build_sdist, args.sdist)) if chosen or not (args.wheel or args.sdist)]
    previous = Path.cwd()
    os.chdir(root)
    try:
        for builder in builders:
            print(outdir / builder(str(outdir)))
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(previous)
    return 0


if __name__ == "__main__":
    sys.exit(main())
