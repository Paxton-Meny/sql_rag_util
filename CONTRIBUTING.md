# Contributing

Issues are welcome: bug reports, questions, and proposals. Pull requests from outside the project are not accepted and are closed without review. The code is offered under a noncommercial license with commercial use by permission, and taking in code written by others would tie that permission to their consent. If you have a fix in mind, describe it in an issue; the change will be made in the repository with credit to you in the changelog.

## Issues

- **Bugs.** Use the bug report form. Include the `sql_rag_util` version, Python version, dialect, and driver with its version, the tool or SDK call with its arguments, and what you expected. A failing `unittest` case is ideal. Leave out real data and credentials.
- **Proposals.** Use the feature request form. Describe the agent-facing command or metadata field, its arguments, and its response shape. The package depends on nothing and will stay that way.
- **Security.** Never in a public issue. Report privately as described in [SECURITY.md](SECURITY.md).

## How the project is built

For anyone reading or forking the code, these are the rules every change follows.

- The package, its tests, and its build use the Python standard library only. Development runs in a virtual environment managed by [uv](https://docs.astral.sh/uv/), never the system Python, and nothing is installed into it.
- No arbitrary SQL. Every statement the package emits comes from a fixed template in the dialect layer, with identifiers validated against the catalog and values bound as parameters.
- Python 3.11 or newer. Every signature is annotated, public surfaces carry numpydoc docstrings, and there are no inline comments; explanation goes in docstrings and `docs/`. `tests/test_conventions.py` enforces these.
- One logical change per commit and per pull request, with the changelog updated in the same branch. History stays linear.

Set up a clone with `uv venv --python 3.11` (any Python 3.11 or newer) and `git config core.hooksPath .githooks`, then run the gate from the repository root:

    uv run --no-project python -m compileall -q sql_rag_util tests buildsys benchmarks && uv run --no-project python -m unittest discover -s tests -t . -q

The pre-commit hook runs the same gate and refuses to run without uv and `.venv`.

## Tests

`unittest`, under `tests/`, mirroring the package. SQLite runs in-process. PostgreSQL, MySQL, and SQL Server run end to end through scripted drivers that answer introspection and check every statement and bound value. Nothing in the suite needs a database server, and CI runs it on Python 3.11 to 3.14 without any external action.
