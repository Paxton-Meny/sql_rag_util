# information_schema first, native catalogs where it is silent

## Decision

Columns and foreign keys come from information_schema on MySQL, SQL Server, and PostgreSQL. Row estimates come from `TABLES.TABLE_ROWS`, `sys.partitions`, and `pg_class.reltuples`, and PostgreSQL extension presence from `pg_extension`, because information_schema has no equivalent.

## Alternative weighed

Native catalogs everywhere, or information_schema only.

## Why the alternative lost

information_schema is the portable surface and keeps three dialects nearly identical, but it cannot answer the two questions the cards and the capability probe need. Naming the exceptions keeps the deviation deliberate and small.
