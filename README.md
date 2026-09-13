# sql_rag_util

A dependency-free Python module that lets AI agents, tools, and workflows retrieve from arbitrary tables in a SQL database safely and at low token cost. Agents never write SQL. They call a small set of predefined, parameterized commands (list tables, describe columns and types, describe relationships, read developer-added metadata, and opt-in fuzzy search over approved columns), and receive only the slice of schema or data they asked for. Developers use it as an SDK to build tools tailored to their own application, and describe what the schema alone cannot say in a documented Markdown metadata format or through the bundled toolkit.

## Status

Pre-alpha. The public API does not exist yet and nothing here is stable. Watch the changelog.

## Install

There is no package release yet. Copy or submodule the `sql_rag_util/` directory into your project. It needs Python 3.11 or newer and nothing else; database access goes through the PEP 249 connection you already have.

## Usage

Examples arrive with the first release.

## Project structure

- `sql_rag_util/`: the package.
- `tests/`: `unittest` suite mirroring the package.
- `docs/`: metadata format specification, threat model, design decisions, and the agent command reference.
- `.githooks/`: the pre-commit gate. Activate once per clone with `git config core.hooksPath .githooks`.

## Development

Run the gate from the repository root:

    python3 -m compileall -q sql_rag_util tests && python3 -m unittest discover -s tests -t . -q

See CONTRIBUTING.md for conventions and SECURITY.md for reporting.

## License

PolyForm Noncommercial 1.0.0. Noncommercial use, modification, and redistribution are permitted with the notice retained. Commercial use needs written permission from the author. See LICENSE.
