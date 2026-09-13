# Schema cards follow the M-Schema idea

## Decision

A table is described as one heading line, one line of columns with kind, key role, flags, and known values, a relationship line, and concept and measure lines. Prose appears only in the full card.

## Alternative weighed

DDL statements or verbose per-column paragraphs.

## Why the alternative lost

Compact typed lines with sample values were shown to help models more than DDL while costing fewer tokens, and the same shape serves both `describe_table` and the budgeted context pack. Prose is kept where an agent asked for it.
