# SQLite introspection through pragma table-valued functions

## Decision

SQLite columns and foreign keys are read with `pragma_table_xinfo(?)` and `pragma_foreign_key_list(?)`, which accept a bound table name.

## Alternative weighed

`PRAGMA table_info(name)`, which requires the name inside the statement text.

## Why the alternative lost

The PRAGMA form cannot take a parameter, so the table name would have to be formatted into SQL text. The table-valued functions keep the no-formatting rule intact at the cost of a SQLite 3.16 floor, which the function-list probe raises to 3.30.
