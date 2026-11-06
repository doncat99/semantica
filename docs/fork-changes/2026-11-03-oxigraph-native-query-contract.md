# Native Oxigraph query and atomic-update contract

- Date: 2026-11-03
- Status: implemented; focused verification recorded below. G1 is not passed.
- Inspected fork: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
- Native owner: `semantica/triplet_store/oxigraph_store.py::OxigraphStore`
- Upstream comparison: local merge-base `0a2731c8223426efaa0dd9e9b345a8411ff3d4f0`

## Reason and selected ownership

The user selected upstream's existing embedded Oxigraph owner, with field
fidelity and bounded-read verification before replacing fork snapshot storage.
The existing wrapper can persist RDF, but did not forward native query
substitutions, reject excessive result materialization, or expose native atomic
updates. Callers previously needed to reach into `.store.update` directly.
Repair this owner instead of adding another database, JSON aggregate or adapter.

This record supersedes the earlier audit's statement that the Oxigraph wrapper
was unchanged **for subsequent working-tree changes only**; the historical
capability audit remains accurate for its inspected input.

## Implementation and affected callers

- `execute_sparql` forwards PyOxigraph RDF term substitutions. In PyOxigraph
  0.5.13, substituted SELECT variables must appear in the SELECT projection.
- Optional positive integer `max_rows` and `max_bytes` reject overflow with a
  processing error; they never silently truncate knowledge results. Byte count
  is compact UTF-8 JSON of returned record values, excluding response envelope.
  SELECT, ASK and CONSTRUCT preserve their existing response shapes.
- `execute_update` uses native atomic SPARQL update. Persistent stores flush
  before returning. A flush failure explicitly reports that the update has
  already committed, rather than suggesting it rolled back.
- Updates accept trusted templates. Dynamic RDF terms must use native
  `NamedNode`/`Literal` serialization, as exercised by the injection regression;
  the native update API does not support query substitutions.
- Existing generic TripletStore query delegation forwards query options. Its
  default query cache is not qualified for the new project-sensitive contract:
  production adoption must bypass that cache or repair its identity/invalidation
  in its native owner, with no alternate cache. These tests use OxigraphStore
  directly; they do not assert that generic query caching is safe.
- No business writer/reader switched yet; no artifact pins, dependency manifests,
  formal data or model calls changed. No snapshot substitute was introduced.

## Verification

The new substitution/budget/update specifications first failed on the prior
wrapper: **8 failed, 12 deselected**, 1.35 seconds. The first combined green run
after the field fixture used native SELECT substitution correctly was
**24 passed**, 3.45 seconds, across:

```text
.venv/bin/python -m pytest -q tests/triplet_store/test_oxigraph_store.py tests/test_native_persistence_audit.py
```

Additional tests cover native-serialized hostile Unicode update literals and
the committed-but-flush-failed state. The combined run including those tests
and the 1k/100k point-query probe passed **27 tests in 15.21 seconds**.
The separate persistence audit records three-process qualified-fact fidelity,
shared support withdrawal, and 1k/100k scoped native point-query measurements.

## Limits and remaining gates

### 2026-11-03 query delegation correction

The generic QueryEngine cache concern above has since been repaired in its
existing owner: execution options bypass the query-text-only cache for both
lookup and insertion. See `2026-11-03-native-query-cache-scope.md` for the five
red specifications and native public-entry regressions. Combined Oxigraph,
persistence, QueryEngine, TripletStore and injection suites passed **94 tests
in 16.84 seconds**. This does not qualify production migration or arbitrary
queries. `TripletStore.execute_query(parameters=...)` still silently ignores
that argument; the verified native binding option is `substitutions`.

These caps bound retained Python result records. They do not bound native
planner allocations, physical disk reads, the size of an already-created RDF
term, the complete transport envelope, execution duration or cancellation.
No caller may label an arbitrary SPARQL query bounded merely by passing caps or
adding LIMIT. Production field admission must bound each value, and read APIs
must use scoped indexed patterns with measured budgets. Queries whose record
budget is exceeded fail explicitly and require proper continuation.

This is native capability repair, not completion of the field whitelist,
Docling range reader, crash-safe cross-index visibility, host protocol migration,
paid-result reuse, G2–G8, ESG acceptance or package qualification. The Mac
optional audit installation is not an immutable cross-platform release pin.

## Upstream merge assessment

Disposition: **adapt**. If upstream exposes the same capabilities, reuse its
owner/API and remove redundant fork changes. Re-run native-term binding,
overflow, transaction/flush and process-restart tests against the selected
upstream version. No parallel storage implementation may be retained.

## 2026-11-04 public entry correction

The earlier `parameters` limitation has been repaired by explicit rejection;
native bindings use `substitutions`. The existing QueryEngine optimizer also
no longer silently injects LIMIT 1000 or rewrites literal/comment whitespace.
Red specifications and the 71-test focused result are recorded in
`2026-11-03-native-query-cache-scope.md`. These shared-owner repairs do not
change the resource and integration limitations above.
### 2026-11-04 explicit literal fidelity correction

The existing native `_object_from_triplet` inferred an IRI from URL-shaped text
before checking declared literal datatype/language. Three red tests reproduced
the resulting literal-to-entity type loss. Explicit datatype/language now takes
precedence; `_literal_metadata` retains `xsd:string` for IRI-shaped literals so
read/reinsert/delete preserve the native term. Existing unannotated entity IRIs
keep their current interpretation. No parallel store or automatic type guessing
was added. All five triplet-store focused files passed: **96 passed / 1.93s**.
These are native CRUD/query regressions, not full consumer or release acceptance.
