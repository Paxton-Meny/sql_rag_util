# Metadata format, version 1

This is the normative specification of the per-project metadata that sql_rag_util reads. Metadata adds only what the schema does not imply: purposes, synonyms, column meaning and flags, relationships the database does not declare, business concepts, measures, and glossary terms. The parser is strict. Anything this document does not permit is an error that names the file and line.

## Layout

```
<root>/
  project.md
  tables/<table>.md
  tables/<schema>.<table>.md
  relationships.md
  glossary.md
```

`<root>` is chosen by the developer. Every path is resolved and must stay inside the root. A table file is named by the bare table name when that name is unique across the loaded schemas and by `<schema>.<table>` otherwise. A table file for a table that is not in the catalog is an error. `project.md`, `relationships.md`, and `glossary.md` are optional; a table file is optional per table.

## Common rules

- UTF-8, LF line endings, no tabs.
- Every file starts with a level-one heading followed by a blank line and then `format: 1`. Any other version is an error.
- Header keys are `key: value` lines that follow `format:` without a blank line between them. Unknown keys are errors.
- Sections are level-two headings from the fixed set for that file. Unknown sections are errors. A section may appear at most once. Order does not matter.
- Bullets are `- ` at column zero. Sub-bullets are `  - ` indented two spaces. A bullet's or sub-bullet's text may continue on following lines indented by two or more spaces.
- Prose sections hold plain paragraphs. Nothing in them is interpreted.
- A value that is a list is comma separated. Whitespace around items is trimmed. An item that needs a comma is not supported.

## project.md

```
# project

format: 1
description: Order management for the web shop.
value_index: on
value_index_max_distinct: 200
samples_per_column: 3
```

| Key | Required | Meaning |
| --- | --- | --- |
| `description` | no | One paragraph shown to agents in `get_context` when the budget allows |
| `value_index` | no | `on` or `off`, default `off`. Enables the value index and column samples |
| `value_index_max_distinct` | no | Integer, default 200, maximum 1000. Columns with more distinct values keep samples only |
| `samples_per_column` | no | Integer, default 3, maximum 10 |

## tables/<table>.md

```
# orders

format: 1
purpose: One row per customer order.
synonyms: purchase, sale

## Description

Amounts are in the customer's currency at the time of the order. Cancelled
orders keep their rows.

## Columns

- id: Surrogate key.
- customer_id: The buyer.
- status: Lifecycle state.
  - values: open, paid, shipped, cancelled
  - synonyms: state, stage
- email [sensitive]: Contact address at the time of the order.
- internal_notes [hidden]: Staff notes.
- shipping_name [searchable]: Recipient name as printed on the label.
  - source: agent, 2026-09-13

## Relationships

- customer: The buyer. Renames the generated relationship to customers.
- shipments: Shipments for this order.

## Concepts

- active: Orders that still need attention.
  - where: [{"column": "status", "op": "in", "value": ["open", "paid"]}]
- last_30_days: Orders placed in the last thirty days.
  - where: [{"column": "created_at", "op": "since_days", "value": 30}]

## Measures

- revenue: Sum of order amounts.
  - expr: {"fn": "sum", "column": "amount"}
```

The heading must equal the file's stem. `purpose` is required and is one line; it is the text `list_tables` and schema cards show. `synonyms` is optional.

Sections: `Description` (prose), `Columns`, `Relationships`, `Concepts`, `Measures`.

### Columns

Bullet grammar: `- <name>[ [<flag>, ...]]: <text>`. The name must be a column of the table. Flags:

| Flag | Effect |
| --- | --- |
| `searchable` | `search_rows` may match this column. Text kinds only |
| `sensitive` | Never selected, filtered, ordered, grouped, searched, indexed, or sampled. Shown by name in `describe_table` with the flag |
| `hidden` | Absent from every output and every predicate |
| `fulltext` | A full-text index exists on this column; enables the dialect's full-text strategy |

`sensitive`, `hidden`, and either of `searchable` or `fulltext` are mutually exclusive. Sub-bullets: `values:` (a list of the meaningful values, shown in cards), `synonyms:` (a list), `source:` (`agent, YYYY-MM-DD` or `developer`; absent means developer).

### Relationships

Bullet grammar: `- <name>: <text>`. The name must be a relationship the catalog generated or one declared in `relationships.md`. The text replaces the generated description. To rename a generated relationship, add a sub-bullet `- renames: <generated name>`.

### Concepts

Bullet grammar: `- <name>: <text>` with a required sub-bullet `- where: <JSON array>`. The array holds filter objects `{"column", "op", "value"}` exactly as the `query` tool accepts them, validated against the table's columns and the operator whitelist. A concept name is a lowercase identifier and must not collide with a column name. Concepts may reference dotted columns through relationships to the same depth the `query` tool allows.

### Measures

Bullet grammar: `- <name>: <text>` with a required sub-bullet `- expr: <JSON object>` of the form `{"fn": <count|count_distinct|sum|avg|min|max>, "column": <name>}`. `count` may omit `column`. Kind gates apply. A measure name must not collide with a column or concept name.

## relationships.md

```
# relationships

format: 1

## order_shipments

from: orders (id)
to: shipments (order_id)
cardinality: to_many
text: Shipments for an order. No foreign key exists because shipments arrive from a feed.
```

Each level-two heading is a declared relationship name. Keys: `from` and `to` as `<table> (<column>, ...)` with matching column counts, `cardinality` as `to_one` or `to_many` read from the `from` side, and `text`. Tables and columns must exist in the catalog. A declared name must not collide with a generated relationship on the `from` table.

## glossary.md

```
# glossary

format: 1

## Terms

- SKU: Stock keeping unit, the product identifier printed on labels.
  - synonyms: product code, item number
  - tables: products, order_lines
```

The single section is `Terms`. Bullet grammar: `- <term>: <definition>`. Sub-bullets: `synonyms:` (a list) and `tables:` (a list of tables the term relates to, used for retrieval). Terms are unique case-insensitively.

## Provenance

Every entry written through the toolkit carries `source: agent, <date>`. Developer-written entries carry no `source` line or `source: developer`. The toolkit never removes `sensitive` or `hidden`.

## Canonical form

The writer emits files in the order shown above, with one blank line between blocks, keys in the documented order, and lists joined by a comma and a space. Parsing a canonical file and writing it again produces identical bytes.
