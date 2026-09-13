# Architecture

sql_rag_util lets AI agents retrieve from arbitrary SQL tables without writing SQL. Agents call a small set of tools; the package compiles each call into one bounded, parameterized statement against a catalog it introspected. Developers use the same code as an SDK and add project context through a Markdown metadata format that agents can also maintain.

## Principles

1. No SQL text from outside. Builders are pure functions from (dialect, catalog, validated arguments) to a `Statement` of fixed fragments and `Bind` values. There is no `execute_sql` and no debug path that adds one.
2. Identifiers exist before they are quoted. Every table and column name resolves against the introspected catalog, then the dialect quotes it. The package never emits `SELECT *`; column lists come from the catalog minus hidden and sensitive columns.
3. Values are always bound, limits included. One renderer turns a `Statement` into the driver's paramstyle. Placeholders are never rewritten inside SQL text.
4. Sensitive means invisible to predicates. A sensitive column cannot be selected, filtered, ordered, grouped, searched, indexed, or sampled. A hidden column does not exist to the agent.
5. Metadata is code. The format is strict and versioned, round-trips exactly, is written atomically, stays inside its root, and is validated against the catalog.
6. Results are deterministic. Every data query orders by primary key when the agent gives no order. Pagination is keyset, through filters. There is no OFFSET.
7. Every statement is bounded: row cap, cell cap, column cap, join depth cap, group and measure caps, value index cardinality cap.

## Agent surface

Five read tools, exposed in tiers so a framework loads only what it needs. `minimal` is `get_context` and `query`; `standard` adds `describe_table`, `list_tables`, and `search_rows`; `full` adds the metadata toolkit.

| Tool | Purpose |
| --- | --- |
| `get_context(question, budget_tokens)` | Ranked schema cards for the tables that matter, value hits, matching concepts and glossary entries |
| `list_tables()` | Name, purpose line, approximate rows |
| `describe_table(table)` | Full schema card: columns, kinds, keys, relationships, concepts, measures, prose |
| `query(spec)` | One declarative read: columns, filters, joins by relationship name, group_by, measures, order, limit |
| `search_rows(table, term)` | Fuzzy retrieval over searchable columns, strategies chosen by dialect capability |

The `query` spec is a small semantic layer. Counts, distinct values, and relationship traversal are idioms of the same spec, so the agent learns one shape. Named concepts (developer-defined filters) and measures come from metadata and are validated against the catalog before they can be used.

Every result is an envelope: `columns`, `rows`, `truncated`, `schema_version`, and `notes`. Notes carry fan-out warnings, suggestions when a query returns nothing, and narrowing advice when it was truncated. Errors carry a type, a message, and suggestions such as close-match names, so an agent corrects itself in one round trip.

## Retrieval

`get_context` ranks tables from three sources: lexical scoring (BM25 with field weights) over identifiers and metadata text, value retrieval through an opt-in index of low-cardinality column values, and an optional developer-supplied embedding function. Ranks are fused by reciprocal rank fusion. Tables one relationship hop from the top hits are added while the budget allows. Cards are emitted in rank order until the token budget is spent.

Schema cards are compact: one line per column with kind, key role, and a few example values; relationship lines by name; applicable concepts and measures. A `schema_version` fingerprint over catalog, metadata, and value index tells the agent when cached knowledge is stale.

## Layers

```
commands/    tool specs, JSON schema derivation, dispatch, text rendering, instructions
adapters/    tool definition shapes for Anthropic, OpenAI strict, and MCP
mcp/         JSON-RPC 2.0 stdio server, standard library only
engine.py    SqlRag facade: connection, dialect, catalog, metadata, config, commands
retrieval/   tokenizing, BM25, value index, embedding hook, rank fusion, cards, context pack
search/      term handling, fuzzy strategies, Soundex, Levenshtein, SQLite function registration
query/       query spec, filters, joins, aggregates, ordering, scope, compilation to one Statement
metadata/    model, strict parser, canonical writer, contained store, catalog annotation, concepts
schema/      catalog model, introspection, relationship derivation, name resolution, cache
dialects/    quoting, limit form, introspection statements, type kinds, fuzzy predicates, detection
sql/         Statement and Bind, rendering to each paramstyle
executor.py  the only module that calls cursor.execute; never commits
```

Each layer depends only on the layers below it. Builders do no I/O. The executor is the single execution site, which is where the audit hook, row and cell limits, and JSON coercion live.

## Dialects

SQLite, MySQL and MariaDB, Microsoft SQL Server, and PostgreSQL. The dialect is detected from the connection's driver module; an explicit `dialect` argument wins, and a driver that connects to anything (pyodbc) requires it. Each dialect owns its quoting rule, its limit form (`LIMIT ?`, or `TOP (?)` on SQL Server), its introspection statements, its native type to kind mapping, and its fuzzy predicates. Everything else is shared.

## Metadata

A directory of Markdown files: `project.md`, one file per table, `relationships.md`, `glossary.md`. It carries only what the schema does not imply: purposes, synonyms, column descriptions and flags (searchable, sensitive, hidden, fulltext), declared relationships, concepts, measures, and glossary terms. See `metadata-format.md`. The toolkit tools edit these files by loading, replacing, and rewriting them canonically; entries an agent adds carry their provenance.

## Testing

SQLite in process is the only live database. Every other dialect is tested by asserting the exact statement text and bound parameters the package emits through a fake cursor. Pure functions are table-driven. Security properties are named tests. Context cost is measured by a benchmark and capped by tests.
