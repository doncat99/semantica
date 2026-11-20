# Source-scoped native hybrid knowledge query

- Record ID: 2026-11-19-native-hybrid-query
- Date / author: 2026-11-19 / Codex
- Status: implemented; focused native verification passed; consumer adoption pending
- Fork base revision: a6a716d2dbedf9c220b1048f901c4c00e2d06203 (main, unrelated Explorer edits preserved)
- Upstream reference: not inspected
- Related consumers: Auto Marketing V2 WP3; no consumer pin change yet

## Reason and scope

The worker accepts keyword or semantic queries, but cannot combine them. Auto
Marketing must not build a host-side ranking implementation. Add explicit bounded
hybrid retrieval of native knowledge objects. Document occurrence fusion is not
included because occurrence and canonical record ranking have different units.

## Native capability assessment

- `semantic_query.py::query_semantic_artifact` owns publication admission, lexical
  or vector selection and hydration; `semantic_query_schema.py` owns the protocol.
- `explorer/search_index.py::GraphSearchIndex.search_native_positions` scopes before
  occurrence retrieval. `PublicationRecords.grounded_candidates` joins exact scalar
  addresses to canonical IDs/evidence. `SQLiteVecStore.search_native_records` scopes
  before grouped vector ranking. Reuse these owners without changing algorithms.
- `vector_store/hybrid_search.py::SearchRanker.rank` owns RRF. Reuse it directly;
  do not use aggregate `ContextRetriever` or introduce another fusion formula.
- Actual callers/tests inspected: `semantic_query_worker.py` dispatch and serving
  thread initialization; `tests/test_native_query.py`, `tests/test_semantic_query_worker.py`.
- Recent query changes inspected: b6912a6c, be868dec, b877493d, bf0b71be, 35510765.
  Retired aggregate snapshot retrieval remains retired.
- Decision: extend the existing native query owner, reuse existing fusion owner.

## Approach and actual changes

Planned: explicit `hybrid` mode requires both indexes and a supplied query
embedding; scoped lexical positions join canonical records before RRF with scoped
vector records. Preserve evidence union, channel ranks, candidate bounds and
immutable generation pagination. No model/network call or rebuild at query time.
No host inference, source fallback, additional dependency or publication mutation.

## Verification and limitations

Pending regression reproduction and implementation. Consumer runtime uses a pinned
wheel and will not load this checkout. This change alone cannot qualify temporal
maintenance, real-world recall, identity resolution or business adoption.

## Upstream merge assessment

- Disposition: pending; upstream not reviewed.
- Overlaps: native query protocol/coordinator, worker lazy vector initialization.
- Reuse an upstream native equivalent if introduced; remove duplicate fusion paths.
- Re-run native query/worker and affected consumer protocol qualification after merge.


## 2026-11-19 implementation and verification update

The planned native extension is implemented in `semantic_query.py`,
`semantic_query_schema.py`, and `semantic_query_worker.py`. Hybrid knowledge
queries reuse `SearchRanker.rank` for RRF (k=60), merge canonical IDs and union
source/evidence refs, and expose per-channel ranks and bounded-candidate metadata.
Lexical positions, distinct grounded records and vector records are bounded at
128; oversize grounded results fail explicitly. Fused pagination is limited to
that candidate pool and does not promise exhaustive search. The worker initializes
vectors lazily on its serving thread for both semantic and hybrid requests.
Publication readmission/cancellation also applies before an empty early return.

Regression reproduction before the implementation: two hybrid query tests failed,
one existing comparison test passed. After implementation, one initial test assumed
the top fused item was keyword rank 1; the native fixture correctly returned
keyword rank 2 / semantic rank 1. The assertion was corrected to check those actual
ranks and the existing ranker's RRF score, without changing ranking behavior.

Verification in the native checkout virtualenv:

```sh
.venv/bin/python -m pytest -q tests/test_native_query.py tests/test_semantic_query_worker.py tests/test_native_document_reader.py tests/vector_store/test_hybrid_search_filter_kwarg.py tests/vector_store/test_sqlite_vec_store.py tests/triplet_store/test_publication_records.py --tb=short
```

Result: **170 passed in 22.03s**. `git diff --check` passed. Tests cover real local
native stores, source scope, evidence, deterministic pagination/reopen, stale
indexes, invalid modes/bounds, bounded fusion, and lazy initialization. Fixtures
are engineering evidence, not independent retrieval-quality evaluation.

The earlier pending paragraph records the original plan. It is superseded for
implementation status by this dated update. No wheel has been released, no
consumer pin changed, and Auto Marketing's installed artifact still has no hybrid
mode. Full release, relocated artifact installation, consumer protocol, real-data
semantics, temporal maintenance and business adoption remain unqualified. Unrelated
Explorer source and test artifacts remain untouched. Upstream remains unreviewed.
