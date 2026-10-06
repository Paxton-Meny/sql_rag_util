# sql_rag_util

A dependency-free Python module that lets AI agents, tools, and workflows retrieve from arbitrary tables in a SQL database safely and at low token cost. Agents never write SQL. They call five tools (find the tables that matter, describe one, list them, run one declarative query, search rows fuzzily), and the package compiles each call into one bounded, parameterized statement against a catalog it introspected. Developers use the same code as an SDK, add what the schema cannot say through a small Markdown metadata format, and let agents record what they learn through a validated toolkit.

## Status

0.1.0. The API is young and will change between minor versions until 1.0. SQLite is tested live; MySQL and MariaDB, SQL Server, and PostgreSQL are tested by asserting the exact SQL they emit.

## Install

Copy or submodule the `sql_rag_util/` directory into your project, or add the repository root to your path. It needs Python 3.11 or newer and nothing else; database access goes through the PEP 249 connection you already have.

## Usage as an SDK

```python
import sqlite3
from sql_rag_util import Config, SqlRag, register_sqlite_functions

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

Every tool is also reachable through `engine.dispatch(name, arguments)`, which returns a JSON envelope with `schema_version`, `truncated`, and `notes`, or an error with suggestions the agent can act on. `engine.dispatch_text` returns a compact tab-separated form.

For PostgreSQL, MySQL, or SQL Server pass the driver's connection the same way; the dialect is detected from the driver module, and drivers that connect to anything (pyodbc) take `dialect="mssql"` explicitly.

## Usage with an agent framework

```python
from sql_rag_util.adapters import anthropic, openai, mcp

system_prompt = engine.instructions()
tools = anthropic.tool_definitions(engine, tier="standard")
functions = openai.tool_definitions(engine)
```

When the model calls a tool, hand the name and arguments to `engine.dispatch`. Tiers: `minimal` exposes `get_context` and `query`; `standard` adds `describe_table`, `list_tables`, and `search_rows`; `full` adds the metadata toolkit when `Config(allow_metadata_writes=True)`.

## Usage as an MCP server

```bash
python3 -m sql_rag_util.mcp --sqlite shop.db --metadata sqlrag_metadata
```

Serves the tools over stdio to any MCP client with no installation. Other databases: build a `SqlRag` with the driver's connection and call `sql_rag_util.mcp.server.serve_stdio(engine)`.

## Metadata

A directory of Markdown files adds what the schema does not imply: purposes, column meaning and known values, searchable and sensitive flags, relationships the database does not declare, named concepts (business rules as filters), named measures, and a glossary. The format is specified in [docs/metadata-format.md](docs/metadata-format.md); reference files live under `tests/fixtures/metadata/`. Turning on the value index in `project.md` lets `get_context` map words in a question to the columns holding them.

## Safety

No arbitrary SQL, ever. Names are resolved against the catalog before they are quoted, values and limits are always bound, sensitive columns are refused in every position, hidden columns do not exist, every statement is capped, and the package never commits. See [docs/threat-model.md](docs/threat-model.md).

## Project structure

- `sql_rag_util/`: the package. `engine.py` is the facade; `commands/` the tools; `query/` the spec and compiler; `dialects/` the four databases; `schema/` introspection; `metadata/` the format; `retrieval/` and `search/` schema and row retrieval; `adapters/` and `mcp/` integrations.
- `tests/`: `unittest` suite mirroring the package; `tests/support/fixture.py` is the shared SQLite database.
- `docs/`: architecture, threat model, metadata format, tool reference, SDK surface, context cost, and design notes.
- `benchmarks/`: the context-cost script.
- `.githooks/`: the pre-commit gate. Activate once per clone with `git config core.hooksPath .githooks`.

## Development

Run the gate from the repository root:

    python3 -m compileall -q sql_rag_util tests && python3 -m unittest discover -s tests -t . -q

See CONTRIBUTING.md for conventions and SECURITY.md for reporting.

## License

PolyForm Noncommercial 1.0.0. Noncommercial use, modification, and redistribution are permitted with the notice retained. Commercial use needs written permission from the author. See LICENSE.
