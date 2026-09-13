# Rows are arrays under a column list

## Decision

Results are `columns` plus `rows` as arrays in column order, and a tab-separated text form.

## Alternative weighed

A list of objects with a key per cell.

## Why the alternative lost

Repeating every column name on every row costs roughly forty percent more tokens on a typical result. The compact text form is cheaper still and is what MCP clients receive as content.
