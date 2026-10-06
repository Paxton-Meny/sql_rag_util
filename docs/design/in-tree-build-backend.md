# An in-tree build backend

## Decision

`pip install` builds the package with `buildsys/sql_rag_util_build.py`, a standard-library module that implements the PEP 517 and PEP 660 hooks, declared as `[build-system] requires = []` with `backend-path = ["buildsys"]`. It reads the `[project]` table with `tomllib`, refuses any key it does not support, any dependency, and any version that differs from `sql_rag_util.__version__`, and writes core metadata 2.4 with an SPDX `License-Expression`. Wheels and sdists are reproducible: entries are sorted, timestamps come from `SOURCE_DATE_EPOCH` or a fixed date, and owners and modes are fixed. Editable installs use an import hook that exposes `sql_rag_util` alone rather than a path entry that would also expose `tests`.

## Alternative weighed

Declare setuptools, or another published backend, as the build requirement.

## Why the alternative lost

The project depends on nothing, and a build requirement is a dependency in everything but name: pip downloads and runs it on every install from source, and it changes with each release. This project needs a small fraction of what a general backend does, and the formats it writes (wheel, sdist, core metadata, `RECORD`) are short published specifications. A module of a few hundred lines, tested against those specifications and proven against pip's own installer in CI, keeps installation free of anything the project did not write. The cost is that new `[project]` keys need backend support before use, which the refusal makes impossible to miss.

## Limits

Byte-identical wheels assume the same zlib on both machines; a different deflate implementation produces equal contents in different bytes. The metadata version stays at 2.4, not the newest, so older bundled pips accept it.
