# The MCP server is standard library only

## Decision

JSON-RPC over newline-delimited stdio with initialize, ping, tools/list, and tools/call is implemented directly.

## Alternative weighed

Depend on an MCP SDK.

## Why the alternative lost

The subset the toolkit needs is about two hundred lines, and a dependency would break the project's one hard rule. The server opens SQLite read-only and any other database through a five-line Python entry point.
