## Summary

## Changes

## Closes

Closes #

## Gate

- [ ] `uv run --no-project python -m compileall -q sql_rag_util tests buildsys benchmarks && uv run --no-project python -m unittest discover -s tests -t . -q` passes
- [ ] No new imports outside the standard library
- [ ] Every emitted SQL statement uses validated identifiers and bound parameters
- [ ] CHANGELOG.md updated
- [ ] Docs updated for any behavior change

## Untrusted input handled

State what agent- or file-supplied input this change touches and how it is validated, or "none".

## Related
