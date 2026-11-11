# Native full-build traversal

- Record ID: 2026-11-11-native-build-traversal
- Date / author: 2026-11-11 / OntoScience contributors
- Status: verified-in-stated-scope
- Fork base revision: bf0b71be59c1b801f61a83fc9d4f9c522aba4e4b
- Upstream reference: not inspected; merge disposition pending
- Related record: 2026-11-11-native-fact-cards.md (completed fact-card prerequisite)

## Reason and scope

Full presentation builds repeatedly used independently paged scene queries. The
native Oxigraph query result already supports incremental iteration; its lifetime
was not exposed across JSONL requests. A single implicit facts/topology cursor
could not safely support interleaved build selections.

## Native capability assessment

Reuse NativeQueryStore's acquired OxigraphStore, PublicationRecords scene owners,
and Oxigraph query iterators. Existing interactive scene consumers retain their
bounded page contract. The full-build worker uses explicit iteration of the same
native query and hydration owners, without another store or semantic algorithm.

## Approach and actual changes

semantic_query.py owns bounded, generation/store/build-bound iterator handles;
semantic_query_schema.py and semantic_query_worker.py expose open/next/close.
PublicationRecords accepts that iterator for existing scene selection and streams
community/topic membership once. One query initialization per selection retains
its native ordering. This does not claim Oxigraph ORDER BY has no materialization
cost; it removes restarting that work for every page. Page budgets reserve the
transport envelope and include continuation identity bytes.

Eight handles maximum, 60-second idle expiry, 128 rows / 256 KiB maximum batch,
bounded lookahead, exact sequence checks, explicit close, release invalidation,
and fail-closed generation checks. No persisted cursor, source migration, model
calls or network calls are introduced. Interrupted consumers must rebuild derived
presentation indexes atomically from source, never resume an expired iterator.

## Verification and limitations

.venv/bin/python -m pytest -q tests/test_native_record_worker.py
 tests/triplet_store/test_publication_records.py
 tests/triplet_store/test_canonical_fact_publication.py: 99 passed before final
continuation-byte accounting adjustment; rerun recorded below. Tests cover 261
native topics/members at 128-row and 2 KiB budgets, exact coverage and exactly two
primary query initializations for the two selections, interleaving, replay,
capacity, foreign build identity, release and cancellation. Installed native model
acceptance also exercises seven interleaved streams after real publication.

Cross-platform artifact qualification and installed host lifecycle acceptance are
recorded in the host implementation record; source tests alone are not release
acceptance. Native ORDER BY internal memory/disk behavior is not proven bounded
by a Python batch limit. This remains an explicit storage-engine limit.

## Upstream merge assessment

Disposition: pending. Incoming upstream revision not reviewed. Compare native
query session, publication scene and member owners before merging; remove this
transport extension if upstream provides the same lifetime and fencing contract.
Rerun interleaved streams and installed host lifecycle tests after any merge.

2026-11-11: final source regression rerun: 98 passed; existing ESG activation
performance gate failed at 11.594 s against 10 s while native artifact validation
and host tests were running concurrently. No activation owner was changed. Kept
the hard gate; isolated rerun follows. Installed interleaving acceptance initially
assumed two nodes, but its fixture publishes two sources. Replaced that incorrect
constant with equality to each existing native scene and exact parent/member
coverage, preserving all completeness and byte assertions.

2026-11-11: isolated activation gate passed (1 test, 11.35 s total fixture plus
activation); original 10 s activation criterion was not modified. Host installed
lifecycle acceptance passed with 7 streams, no scene transport calls and 615 ms
presentation build; deterministic local fixture, not a user-data benchmark.
