# Bound limits and keyset pagination, no OFFSET

## Decision

Every data statement binds its row cap as a parameter (`LIMIT ?`, or `TOP (?)` on SQL Server) and binds one more than requested so truncation is detected. There is no offset argument; an agent pages by adding a filter on the primary key it last saw.

## Alternative weighed

OFFSET ... FETCH or LIMIT ... OFFSET with an offset argument.

## Why the alternative lost

OFFSET forces an ORDER BY on SQL Server, is unstable under concurrent writes, and costs the database the rows it skips. Keyset pagination through a filter the agent can already express is stable and cheap, and keeping the limit bound means the rule that every value is a parameter has no exception to audit.
