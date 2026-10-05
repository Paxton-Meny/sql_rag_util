# Threat model

This document covers every surface that accepts untrusted input. It is updated in the same branch as any change that adds one.

## Assets

- The database the caller connected to: its data, its availability, and the confidentiality of columns the developer marked sensitive or hidden.
- The metadata directory and its cache files on the developer's filesystem.
- The caller's process: its memory, its environment, and its other files.

## Actors

- The agent. Every tool argument is untrusted. The model may be confused, prompted by hostile content it read elsewhere, or simply wrong. It is assumed to try anything the schema of a tool permits and some things it does not.
- Content in the database. Cell values flow back to the agent and may contain text that tries to steer it. The package cannot fix that, but it must never let a cell value become SQL, a filesystem path, or a metadata instruction.
- The developer. Trusted. Configuration, metadata files, scope filters, and the embedding hook run with the developer's authority. Scope filters alone may use hidden and sensitive columns, and their values must come from the application, never from the agent.
- The database server. Trusted for correctness of catalog answers. Not trusted to enforce limits the package promised the caller.

## Surfaces and controls

### Tool arguments

Threat: SQL injection through a name or a value; enumeration of columns the developer hid; unbounded reads.

Controls: every table, column, relationship, concept, and measure name resolves against the catalog before use, and an unknown name is an error carrying close matches rather than a string that reaches SQL. Values are bound through the driver, never formatted. Operators and aggregate functions are whitelisted and gated by column kind. Sensitive columns are rejected in every position, including filters, because a filter on a secret is an oracle. Hidden columns are absent from the catalog the agent resolves against, so naming one fails exactly as a missing column does. Developer scope filters are applied to every statement without passing through the agent, and a broken scope is reported as one generic configuration error that names no column. Row, cell, column, join depth, group, measure, and IN-list caps apply to every statement. Limits are bound values, not text.

### Search terms

Threat: LIKE wildcard abuse; full-text query language injection; unbounded fuzzy scans.

Controls: terms are tokenized with a cap on tokens, escaped for `%`, `_`, and the escape character, and bound per column. SQL Server uses `FREETEXT`, never `CONTAINS`, because `CONTAINS` interprets its argument. Fuzzy strategies run only on columns the developer marked searchable and only when the dialect reports the capability.

### Metadata files

Threat: a crafted file that names a path outside the root, declares a relationship to a table that does not exist, or smuggles an operator the query layer would not accept.

Controls: paths are resolved and checked for containment; symlink escapes and `..` are rejected. The parser is strict: unknown keys, sections, flags, or format versions are errors with file and line. Concepts and measures are JSON validated against the same whitelists and the same catalog as agent-supplied queries. Metadata is trusted only after validation, and a table file for a table not in the catalog is an error.

### Toolkit writes

Threat: an agent rewriting metadata to unmark a sensitive column or to add a concept that leaks data.

Controls: writes are off unless the developer enables them. The `sensitive` and `hidden` flags cannot be removed through the toolkit, only added. Every agent edit carries a provenance line with source and date so a developer can review. Files are rewritten canonically from the model, never edited in place, and written atomically.

### Value index and samples

Threat: data exfiltration through examples; unbounded catalog scans.

Controls: the index is off by default and enabled per project. It never reads sensitive or hidden columns. Each column costs one bounded statement, values are truncated to the cell cap, and columns over the distinct cap keep only samples. Cache files live under the developer's cache directory and are keyed by the catalog fingerprint.

### Caches and filesystem

Threat: cache poisoning; writing outside intended directories.

Controls: cache files are written atomically under the configured cache directory only. A cache whose fingerprint does not match the live catalog is discarded, never merged.

### Connection and dialect

Threat: misdetected dialect producing wrong quoting; session state changes.

Controls: detection maps only known driver modules; ambiguous drivers require an explicit dialect. The package never commits, never changes session settings, and never registers SQLite functions unless the developer calls the registration function.

### Embedding hook

Threat: a developer-supplied function that leaks schema text to a third party.

Controls: this is the developer's choice and authority. The documentation states exactly what text is passed to the hook (identifiers, metadata prose, glossary) and that no cell values are ever sent.

## Out of scope

- Denial of service by many legitimate bounded queries. Rate limiting belongs to the caller.
- A database user with more privileges than the package needs. The documentation recommends a read-only user.
- Prompt injection carried in cell values. The package returns data faithfully; the agent's harness must treat it as data.
