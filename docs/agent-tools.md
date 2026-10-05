# Agent tools

Every tool takes a JSON object and returns an envelope. The JSON envelope is `{"schema_version", "truncated", "notes", ...fields}`; a failure is `{"error": {"type", "message", "suggestions"}}`. Every tool also has a compact text form (`format: "compact"` on the tools that take it, or the text dispatcher) that ends with `note:` lines and `schema_version:`.

Tiers: `minimal` exposes `get_context` and `query`; `standard` adds `describe_table`, `list_tables`, and `search_rows`; `full` adds the metadata toolkit when writes are enabled. `SqlRag.instructions()` returns the workflow block to put in the system prompt.

## query (minimal)

One declarative read compiled to one bounded statement.

| Field | Meaning |
| --- | --- |
| `table` | Table name from `list_tables` or `get_context` |
| `columns` | Bare names or dotted paths through relationships; omitted means every visible column |
| `filters` | `{column, op, value}` objects, AND-ed. Operators: eq ne lt lte gt gte in not_in between contains starts_with is_null not_null since_days |
| `concepts` | Named filters from the table card, AND-ed in |
| `group_by` | Columns to group by, at most two by default |
| `measures` | `{fn, column?, alias?}`; fn is count, count_distinct, sum, avg, min, max, or measure (a named measure from the card) |
| `order` | `{by, direction}` by column path or measure alias; default primary key, or first measure descending when grouped |
| `limit` | Default 50, hard cap 500 |
| `format` | json or compact |

Idioms: count is `measures: [{fn: count}]` with no group_by; distinct values is `group_by: [col], measures: [{fn: count}]`; a join is a dotted path such as `customer.name`.

Result: `table`, `columns`, `rows` (arrays in column order), `row_count`. Notes report fan-out from to_many joins, shortened cells, omitted columns, and empty results. Sensitive columns are refused in every position; hidden columns do not exist.

## describe_table (standard)

`{table, format?}`. Returns the card: `purpose`, `rows`, `description`, `synonyms`, `columns` (`name`, `kind`, `type`, `nullable`, `key`, `fk`, `flags`, `text`, `values`, `synonyms`), `relationships` (`name`, `to`, `cardinality`, `text`), `concepts`, `measures`.

The compact form is a heading line, the description, one line of columns separated by ` | `, a `rel:` line, and `concepts:` and `measures:` lines. The fixture table `orders` renders under 900 bytes.

## list_tables (standard)

`{format?}`. Returns `tables`: `table`, `purpose`, `rows`, `columns` (count). One line per table in compact form.

## search_rows (standard)

`{table, term, columns?, match?, limit?, format?}`. Finds rows whose searchable columns match the term. The term is split into tokens; each token is matched against every searchable column with the strategies the dialect supports, and tokens are combined with `match` (`all` by default, or `any`). Returns the same shape as `query`.

## get_context (minimal)

`{question, budget_tokens?, format?}`. Returns ranked short cards for the tables that matter, `value_hits` (`column`, `value`, `matched`), matching `concepts` and `glossary` entries, within the budget.

## Toolkit (full tier, writes enabled)

`edit_table {table, purpose?, description?, synonyms?}`, `edit_column {table, column, text, values?, synonyms?, searchable?}`, `edit_relationship {table, name, text}`, `edit_concept {table, name, text, where}`, `edit_glossary {term, definition, synonyms?, tables?}`. Each edit is validated against the catalog and written canonically only if the file reads back identically; text fields are single lines and list entries contain no commas. If the files changed on disk since they were loaded, the edit is refused with `MetadataConflictError` and the engine reloads, so a retry applies on top of the change. Column edits carry `source: agent, <date>`. The toolkit never sets or clears `sensitive` and `hidden`.

## Cost

Sizes are measured on the fixture in `tests/support/fixture.py`, capped by `tests/test_cost.py`, and recorded in `docs/context-cost.md`.
