# Deep Relationship scene budget

- Date: 2026-11-17
- Status: implemented; validation recorded below
- Inspected fork revision: 6550b7830195dcf715d07b8804c9aa9fecd0291d
- Upstream reference: not inspected; merge assessment pending

## Reason and Native Owner

OntoScience requests 1024 cards and 512 native links per Deep Relationship
scene page. `PublicationRecords.scene` in `publication_records.py` owns the
native selection, exact membership validation and resource budget. Its existing
128-row validation rejected these requests. Callers are the semantic query
worker and OntoScience's projected scene adapter. Extend this owner in place.

## Changes

Only projected node/link scenes admit up to 1024 rows and selected identities.
Full-record reads, source filters, topology and write batches keep their existing
bounds. Byte budgets, source admission, generation fencing and stable cursors
remain enforced. No stored knowledge migration, model calls or new owner.

## Verification and Limitations

Regression: `test_projected_scene_accepts_1024_nodes_and_512_links_budget`
checks 1024 exact IDs, the native link request, overflow and unchanged full-read
and topology limits. `.venv/bin/python -m pytest -q
tests/triplet_store/test_publication_records.py -k 'scene or projection'`:
9 passed, 68 deselected. Artifact delivery remains open.
Published native binaries require rebuilding before the new contract is available.

## 2026-11-17 Caller Budget Correction

The product display limit must not define a native query limit. The inspected
owner at local revision `98bfa88aee6effb68da1b69f3f267f5d7b0caf54`
still coupled projected rows and selection identities to 1024. Replace that
rule in `PublicationRecords.scene` for node/link reads, including full reads:
the caller supplies `limit`; ID arrays express their own filter cardinality.
Defaults remain 128. Request and response each retain the 262144-byte ceiling;
row materialization is also capped at that transport ceiling (every row needs
bytes). Filters have no product-specific count cap. Exact node selection must
fit the requested row limit. Source membership, duplicate rejection, generation
fences, cancellation and cursors remain enforced. Other scene kinds and write
batches retain their own contracts.

Red evidence: the 1536-row regression failed at the former 1024 check.
After repair, scene/projection selection passes 11 tests (68 deselected),
including caller counts 257/1024/1536, a 1536-ID link filter with limit 7,
cursor continuation and request byte rejection. Host adapter is updated to
the same validation. No new persistence schema or migration is needed.
The earlier 9-test result above documents the superseded count-cap change.
The local native bundle was rebuilt and relocated acceptance passed. Publication
still requires the normal external commit, immutable artifact pin and release
qualification; this checkout remains a source checkout, never an OntoScience
runtime input.

## Upstream Merge Assessment

Pending. Inspect the same native scene owner and rerun scene/projection tests
on merge; remove this change if upstream provides the same contract.
