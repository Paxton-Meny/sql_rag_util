# The value index is opt-in and bounded

## Decision

Known values are read only when `project.md` turns the index on, only for text columns that are neither sensitive nor hidden, with one bounded statement per column and a distinct-count cap; columns over the cap keep a few samples. The index is cached by schema version.

## Alternative weighed

Index every column by default so retrieval works out of the box.

## Why the alternative lost

Reading real data on first use without being asked is a surprise some deployments cannot accept, and unbounded distinct scans are expensive on wide tables. Opt-in with caps keeps the cost predictable and the decision with the developer, while the metadata `values:` lists give agents known values even without the index.
