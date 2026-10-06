# sql_rag_util

A dependency-free Python module that lets AI agents, tools, and workflows retrieve from arbitrary tables in a SQL database safely and at low token cost. Agents never write SQL. They call five tools (find the tables that matter, describe one, list them, run one declarative query, search rows fuzzily), and the package compiles each call into one bounded, parameterized statement against a catalog it introspected. Developers use the same code as an SDK, add what the schema cannot say through a small Markdown metadata format, and let agents record what they learn through a validated toolkit.

## Status

0.2.0. The API is young and will change between minor versions until 1.0. SQLite is tested live. PostgreSQL, MySQL and MariaDB, and SQL Server are tested end to end through scripted drivers that answer introspection and check every statement and bound value, but not against a running server.

## Install

It needs Python 3.11 or newer and nothing else; database access goes through the PEP 249 connection you already have. Install a release straight from the repository:

```bash
pip install "sql_rag_util @ git+https://github.com/Paxton-Meny/sql_rag_util@v0.2.0"
```

The build backend is part of the repository and uses the standard library only, so pip downloads nothing but the source. To build a wheel and an sdist yourself, run `python3 buildsys/sql_rag_util_build.py`, which writes both to `dist/`; `pip install --no-index dist/*.whl` then installs offline. Copying or submoduling the `sql_rag_util/` directory into a project still works too.

## Usage as an SDK

```python
import sqlite3
from sql_rag_util import SqlRag, register_sqlite_functions

connection = sqlite3.connect("shop.db")
register_sqlite_functions(connection)
engine = SqlRag(connection, metadata_root="sqlrag_metadata")

context = engine.run("get_context", {"question": "Which open orders does Acme have?"})
rows = engine.run("query", {
    "table": "orders",
    "columns": ["id", "amount", "customer.name"],
    "filters": [{"column": "status", "op": "eq", "value": "open"}],
})
print(rows.data["columns"], rows.data["rows"], rows.notes)
```

The example assumes a `shop.db` and the metadata from `tests/fixtures/metadata/` copied to `sqlrag_metadata/`. There, `customer` is the name metadata gives the relationship from `orders` to `customers`; without metadata its derived name is `customers_via_customer_id`. `describe_table` lists the names any database has.

`engine.run` returns the raw result and raises on errors. Every tool is also reachable through `engine.dispatch(name, arguments)`, which returns a JSON envelope with `schema_version`, `truncated`, and `notes`, or an error with suggestions the agent can act on. `engine.dispatch_text` returns a compact tab-separated form. [docs/sdk.md](docs/sdk.md) covers the rest of the engine for building your own tools.

For PostgreSQL, MySQL, or SQL Server pass the driver's connection the same way; the dialect is detected from the driver module, and drivers that connect to anything (pyodbc) take `dialect="mssql"` explicitly.

## Usage with an agent framework

```python
from sql_rag_util.adapters import anthropic, openai, mcp

system_prompt = engine.instructions()
tools = anthropic.tool_definitions(engine, tier="standard")
functions = openai.tool_definitions(engine)
```

When the model calls a tool, hand the name and arguments to `engine.dispatch`, with the same tier the definitions came from. Tiers: `minimal` exposes `get_context` and `query`; `standard` adds `describe_table`, `list_tables`, and `search_rows`; `full` adds the metadata toolkit when `Config(allow_metadata_writes=True)`, so a toolkit call is `engine.dispatch(name, arguments, tier="full")`.

## Usage as an MCP server

```bash
python3 -m sql_rag_util.mcp --sqlite shop.db --metadata sqlrag_metadata
```

Serves the tools over stdio to any MCP client with no installation. Other databases: build a `SqlRag` with the driver's connection and call `sql_rag_util.mcp.server.serve_stdio(engine)`.

## Metadata

A directory of Markdown files adds what the schema does not imply: purposes, column meaning and known values, searchable and sensitive flags, relationships the database does not declare, named concepts (business rules as filters), named measures, and a glossary. The format is specified in [docs/metadata-format.md](docs/metadata-format.md); reference files live under `tests/fixtures/metadata/`. `search_rows` only searches columns marked `searchable` (or `fulltext`), so mark at least one per table you want searched. Turning on the value index in `project.md` lets `get_context` map words in a question to the columns holding them; its cache, under `.cache/` in the metadata directory, holds sampled values, so keep it out of version control.

## Safety

No arbitrary SQL, ever. Names are resolved against the catalog before they are quoted, values and limits are always bound, sensitive columns are refused in every position, hidden columns do not exist to the agent, every statement is capped, and the package never commits. Developer scope filters (`Config.scope`) are applied to every statement the agent causes and may use hidden and sensitive columns; take their values from your application's session, never from the agent.

The package is one layer of defence, not the whole of it. Connect as a database user that can only read the tables the agent should reach, and set a statement timeout on the connection, since the package sets none. See [docs/threat-model.md](docs/threat-model.md), including its Deployment section.

## Project structure

- `sql_rag_util/`: the package. `engine.py` is the facade; `commands/` the tools; `query/` the spec and compiler; `dialects/` the four databases; `schema/` introspection; `metadata/` the format; `retrieval/` and `search/` schema and row retrieval; `adapters/` and `mcp/` integrations.
- `tests/`: `unittest` suite mirroring the package; `tests/support/fixture.py` is the shared SQLite database.
- `docs/`: architecture, threat model, metadata format, tool reference, SDK surface, context cost, and design notes.
- `buildsys/`: the standard-library build backend pip uses; see [docs/design/in-tree-build-backend.md](docs/design/in-tree-build-backend.md).
- `benchmarks/`: the context-cost script.
- `.githooks/`: the pre-commit gate. Activate once per clone with `git config core.hooksPath .githooks`.

## Development

Development uses [uv](https://docs.astral.sh/uv/) and a virtual environment: create it once with `uv venv --python 3.11` (any Python 3.11 or newer), activate the hooks with `git config core.hooksPath .githooks`, then run the gate from the repository root:

    uv run --no-project python -m compileall -q sql_rag_util tests buildsys benchmarks && uv run --no-project python -m unittest discover -s tests -t . -q

See [CONTRIBUTING.md](CONTRIBUTING.md) for the conventions every change follows.

## Contributing

Issues are welcome; pull requests from outside the project are not accepted. See [CONTRIBUTING.md](CONTRIBUTING.md), and report security problems privately as [SECURITY.md](SECURITY.md) describes.

## License

[PolyForm Noncommercial 1.0.0](LICENSE). This is a source-available license, not an OSI-approved open-source one. Noncommercial use, modification, and redistribution are permitted with the license and its required notice kept. Commercial use needs written permission from the author; to ask, open an issue titled "Commercial license".
