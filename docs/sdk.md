# Using sql_rag_util as an SDK

`SqlRag` is the one object an application holds. This page lists what it offers beyond `dispatch`, for developers who build their own tools or workflows on the same safety layer. The API is young: names may change between minor versions until 1.0, and every change is in the changelog.

## Building an engine

```python
SqlRag(connection, *, dialect=None, paramstyle=None, metadata_root=None, cache_dir=None, schemas=None, config=Config(), tools=())
```

The connection is any PEP 249 connection. The engine introspects it once, applies the metadata, and never opens, closes, or commits it. `refresh()` re-reads the catalog and the metadata, for example after a migration; a failed refresh leaves the engine as it was.

## Running tools

| Member | Use |
| --- | --- |
| `dispatch(name, arguments, *, tier)` | JSON envelope, or an error envelope for any package error |
| `dispatch_text(name, arguments, *, tier)` | Compact text, or a one-line error |
| `run(name, arguments)` | The raw `CommandResult` at the full tier; errors raise |
| `dispatcher(*, tier)` | A `Dispatcher` bound to this engine, for repeated calls |
| `tool_specs(*, tier)` | The `ToolSpec` objects exposed at a tier |
| `instructions()` | The system-prompt block for this database |

The metadata toolkit is in the `full` tier and appears only with `Config(allow_metadata_writes=True)`; pass `tier="full"` to `dispatch` to reach it.

## Reading what the engine knows

| Member | What it is |
| --- | --- |
| `catalog` | The agent's view: tables, columns, keys, and relationships, with metadata renames and declared relationships applied and hidden columns absent |
| `annotated` | The `AnnotatedCatalog`: the parsed `metadata`, the column `policy`, `searchable` and `fulltext` columns, `concepts`, `measures`, and `full`, the same catalog with hidden columns kept |
| `schema_version` | A hash of the catalog and metadata that agents can use to notice stale knowledge |
| `dialect`, `config`, `limits` | The dialect in use and the configuration it was built with |

Show agents only `catalog`. `annotated.full` exists so trusted developer code, such as scope filters, can reach hidden columns.

## Building blocks for your own tools

| Member | Use |
| --- | --- |
| `executor` | Runs a `Statement` with a bounded fetch, closes the cursor, never commits, and reports to `Config.on_statement` |
| `scope_filters(table)` | The developer scope predicates for a table, already validated |
| `retriever`, `retriever_ready` | The schema and value indexes behind `get_context`, built on first use |
| `store` | The `MetadataStore` over `metadata_root`, or `None` |
| `validate_metadata(metadata)` | Raises unless a `Metadata` value would annotate the live catalog cleanly |

A custom tool is a frozen dataclass of arguments, a handler taking the engine and those arguments, and a `ToolSpec`. Pass it to the engine with `tools=`, and it is served beside the built-in tools by `dispatch`, `tool_specs`, the adapters, and the MCP server, under the same tier and write rules. Reusing the built-in `query` handler keeps the tool on the same compiler, policy, scope, and limits:

```python
from dataclasses import dataclass, field

from sql_rag_util import Filter, QuerySpec, SqlRag
from sql_rag_util.commands.query import query
from sql_rag_util.commands.spec import CommandResult, ToolSpec


@dataclass(frozen=True, slots=True)
class OpenOrdersArgs:
    customer: str = field(metadata={"description": "Customer name, exactly as stored."})


def open_orders(engine: SqlRag, args: OpenOrdersArgs) -> CommandResult:
    spec = QuerySpec("orders", columns=["id", "amount"], filters=[Filter("status", "eq", "open"), Filter("customer.name", "eq", args.customer)])
    return query(engine, spec)


OPEN_ORDERS = ToolSpec("open_orders", "Open orders", "List one customer's open orders.", OpenOrdersArgs, open_orders, examples=({"customer": "Acme Corp"},))
engine = SqlRag(connection, metadata_root="sqlrag_metadata", tools=(OPEN_ORDERS,))
print(engine.dispatch("open_orders", {"customer": "Acme Corp"})["rows"])
```

A tool name already taken, by a built-in or another custom tool, raises `ToolSpecError` before the database is read. Set `mutating=True` on a tool that writes anything, so it is offered only when `Config(allow_metadata_writes=True)`, and `tier` to the smallest tier that should include it.
