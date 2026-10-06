# Context cost

Measured with `python3 -m benchmarks.run` on the fixture database (five tables) and the fixture metadata, at the default limits. Bytes are a proxy for tokens at roughly four bytes per token. `tests/test_cost.py` caps these outputs so a change that inflates them fails the gate.

| Question | Calls | JSON bytes | Compact bytes |
| --- | --- | --- | --- |
| Which open orders does Acme Corp have? | 2 | 3427 | 1158 |
| Revenue by region for active orders | 2 | 3319 | 1094 |
| Find the customer called John Smith | 2 | 3341 | 1053 |
| How many orders per status? | 1 | 183 | 77 |
| tool definitions (standard tier) | 0 | 7773 | 7773 |
| instructions block | 0 | 1170 | 1170 |

Reading the table: a complete question costs one `get_context` and one `query` or `search_rows`, about 1100 bytes in compact form. Tool definitions are the fixed cost per model call; the `minimal` tier cuts it by about a third, to 4895 bytes against 7773. The compact form is about a third of the JSON form because rows carry no repeated keys and cards are single lines.

Measured 2026-10-06 at version 0.2.0. Update this file in the same branch as any change that moves the numbers.
