# Contributing

## Ground rules

- No dependencies. The package, its tests, and its build use the Python standard library only. Development runs in a virtual environment managed by [uv](https://docs.astral.sh/uv/), never the system Python, and nothing is installed into it. A change that adds an import outside the standard library will not be merged without a written justification and prior agreement in an issue.
- No arbitrary SQL. Every statement the package emits comes from a fixed template in the dialect layer with validated identifiers and bound parameters. Pull requests that format SQL from strings are declined.
- Python 3.11 or newer. Annotate every signature. Write numpydoc docstrings. No inline comments; explanation goes in docstrings and `docs/`.

## Workflow

1. Once per clone, create the environment and activate the gate: `uv venv --python 3.11` (any Python 3.11 or newer), then `git config core.hooksPath .githooks`. The hook refuses to run without uv and `.venv`.
2. Branch from `main`: `feat/`, `fix/`, `docs/`, `perf/`, `refactor/`, or `research/` plus a kebab-case slug.
3. Commit atomically. Subject in the imperative, capitalized, 72 characters or fewer, no trailing period, no type prefix. Body explains why when the subject cannot.
4. Run the gate before pushing:

       uv run --no-project python -m compileall -q sql_rag_util tests buildsys benchmarks && uv run --no-project python -m unittest discover -s tests -t . -q

5. Rebase onto `main`, open a pull request, fill the template in full, and update `CHANGELOG.md` in the same branch.
6. Merges are rebase-merge, or squash when the commits are not individually meaningful. History stays linear.

## Tests

`unittest`, under `tests/`, mirroring the package. SQLite runs in-process; every other dialect is tested by asserting the exact statement text and parameters the package emits. Nothing in the suite needs a database server.

## What is accepted

Bug fixes, dialect support that follows the existing dialect layer, metadata format proposals opened as an issue first, and documentation. Feature work starts with an issue describing the agent-facing command, its arguments, and its response shape.
