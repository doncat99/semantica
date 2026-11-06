# Preserve native query bindings and budgets at the public entry

- Record ID: 2026-11-03-native-query-cache-scope
- Date / author: 2026-11-03 / Codex native-owner audit
- Status: verified-in-stated-scope
- Fork base revision: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
- Upstream reference: local merge-base `0a2731c8223426efaa0dd9e9b345a8411ff3d4f0`; remote latest not inspected
- Related records: `2026-11-03-native-persistence-g1-audit`

## Reason and scope

`TripletStore.execute_query` delegates execution options to native `QueryEngine`,
but that owner's existing result cache identifies only prepared query text.
Consequently an unscoped cached query can satisfy a project-bound request,
and a cached large result bypasses a later row/byte budget. Conversely a scoped
result can poison a subsequent unscoped query. This is a correctness and context
isolation defect at the selected native entry, not merely a performance concern.

## Native capability assessment

- Existing owner: `triplet_store/query_engine.py::QueryEngine.execute_query`.
- Inspected caller: `TripletStore.execute_query`; selected backend:
  `OxigraphStore.execute_sparql`, including native substitutions and output caps.
- Decision: repair the existing owner; no alternate cache, query route, RDF
  representation or host-side filtering is introduced.
- `TripletStore.execute_query(parameters=...)` currently ignores its `parameters`
  argument. This is recorded, not silently treated as native binding support.
  The verified current entry uses explicit native `substitutions`; defining or
  changing the unrelated `parameters` contract is outside this repair.

## Approach and actual changes

- `query_engine.py`: calls with execution options bypass both cache lookup and
  cache insertion. Only `graph`, `graphs` and `supports_named_graphs` may use the
  existing cache because dataset preparation already accounts for them in query
  text. Arbitrary future options also bypass caching by default; no expensive
  serialization of native bindings or a second cache key implementation is added.
- `tests/triplet_store/test_query_engine_native_options.py`: exercises the real
  public `TripletStore` entry and embedded backend. Covers project switching
  with identical query text, cache prepopulation, strict row and byte budgets,
  option-result cache pollution and validation of an invalid budget.
- No persistent data/schema migration, dependency change, model or network call.
- Existing query-only cache behavior is retained for calls with no execution
  options; broader cache invalidation on data writes is not resolved here.

## Verification and limitations

Red specification ran before the source fix: **5 failed**. The actual observed
failures included returning both projects instead of the bound one, bypassing
both strict budgets and inserting bound results into the query-only cache. The
final validation test was clarified to assert the native invalid-budget error.

After the source fix:

`.venv/bin/python -m pytest -q tests/triplet_store/test_query_engine_native_options.py tests/triplet_store/test_query_engine.py tests/triplet_store/test_triplet_store.py tests/triplet_store/test_sparql_injection.py`

**67 passed in 0.80 seconds**. This proves option propagation/cache safety in
the stated entry. It does not prove physical engine-read limits, query deadlines,
production corpus performance or full host product acceptance. No packaging,
publication or production data operation was performed.

## Upstream merge assessment

- Disposition: keep while the native query-only cache omits execution options.
- Incoming upstream reviewed: local merge-base only; no remote-latest claim.
- Likely overlap: native QueryEngine result-cache changes.
- Adapt/drop only when the native owner provides equivalent safe binding,
  output-contract and budget handling without fallback or duplicate caching.
- Required regression: public-entry project-isolation and strict-budget tests,
  existing query engine, triplet store and injection suites.

## 2026-11-04 public-entry semantic corrections

The previously recorded silently ignored `parameters` argument is now rejected
before query/cache execution. Native callers use `substitutions`; no second
binding implementation was added. Both empty and nonempty parameters reproduced
the defect before the fix (2 failed), then the focused suites passed 69 tests.

The same native entry's default optimizer appended `LIMIT 1000` and collapsed
all whitespace, including literals and line comments. Two new native tests
reproduced silent loss of the 1001st result and a broken commented query.
`QueryEngine.optimize_query` now delegates planning to the native backend,
preserving query text apart from outer whitespace. Explicit pagination remains
the caller's responsibility; an implicit cap is not a resource budget.
No application caller of `add_limit`/`default_limit` was found in `semantica/`
or the triplet-store tests. The exported optimizer and plan entry use the same
corrected owner. Existing CONSTRUCT templates still delegate directly for
live-read and exception-propagation requirements; no new path was added.

Focused native entry, QueryEngine, TripletStore and injection suites:
**71 passed in 0.58 seconds**. The whitespace test was corrected after the fix
to match the existing native plain-string response shape (no explicit datatype);
its literal content and comment preservation assertions remain. These results
do not close execution/read budgets, cache invalidation on writes, G1 or product
acceptance. Upstream merge: adapt/drop when the upstream native owner preserves
query semantics and rejects unsupported binding contracts equivalently.

## 2026-11-04 mutable native knowledge entry

The selected formal knowledge entry is `TripletStore(backend="oxigraph")`,
delegating to the single embedded owner. It now always constructs its existing
QueryEngine with result caching disabled, including when generic configuration
requests caching. Direct `OxigraphStore.execute_sparql` also has no result cache.
No invalidation registry, write mirror or cache revision is introduced. Native
indexes remain reusable; disabling a result cache does not rebuild an index.

Two red regressions (default config and explicit `enable_caching=True`) returned
an empty cached answer after a durable insert. Both now verify insert/read/delete/
read and an empty result cache. The unrelated generic QueryEngine text cache is
not a permitted knowledge read owner; its use with other backends is not claimed
write-consistent by this remediation. G4 must use the selected native entry,
not construct a separate cached QueryEngine around the embedded backend.

Affected files: `triplet_store/triplet_store.py` and the existing native-options
test. No data/schema/network/model operation. This removes G1's hidden stale-read
path at the selected public entry; it is not production consumer integration.
