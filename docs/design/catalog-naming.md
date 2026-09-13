# The introspected snapshot is a Catalog

## Decision

The frozen snapshot of tables, columns, keys, and relationships is called `Catalog`. The word "schema" is reserved for the database namespace (`TableRef.schema`) and for the JSON Schema of tool arguments.

## Alternative weighed

Call the snapshot `Schema`, as most database libraries do.

## Why the alternative lost

Three meanings of one word inside one package is how a reader confuses a namespace argument with a snapshot and a tool argument schema with either. Catalog is the term the SQL standard already uses for the collection of metadata, and it leaves the other two meanings unambiguous.
