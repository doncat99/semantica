# Retired aggregate-query test owner cut

## Scope and reason

G4 removed aggregate snapshot/query carriers and the JSON process cache. Six
tests in `tests/test_kernel_owner_regressions.py` still required their deleted
fixtures or owners. Delete those tests physically; do not restore `_load_json`,
`ContextRetriever`, `search_groups` query routing, or retrieval-reference files.
This change touches tests and this record only. No product behavior, acceptance
Case, production source, dependency pin, or release artifact changes.

## Invariant and current owner mapping

| Deleted test | Current validation owner |
| --- | --- |
| `test_query_uses_native_vector_ranking` | `tests/test_native_vector_owner_audit.py::test_native_reference_scope_and_vectors_survive_process_restart` verifies scoped SQLite native KNN, rank order, restart, and no matrix reads. `tests/test_native_query.py::test_native_query_preserves_owner_scores_order_and_empty_source_scope` now observes real `search_native_records` routing and forbids `VectorRetriever.search_similar`. |
| `test_query_preserves_native_scores_and_order_without_reranking` | The new native-query test uses the real producer/publication fixture, returns its real native record rows in reversed order with ascending negative scores, and verifies exact IDs and scores after canonical hydration. |
| `test_query_uses_native_keyword_ranking_after_source_admission` | `tests/test_native_query.py::test_actual_native_keyword_two_phase_hydration_and_reopen` verifies address-first selection and canonical hydration. The new native-query test verifies explicit empty source scope in both keyword and semantic modes. `tests/test_native_keyword_owner.py` owns exact occurrence ordering, Unicode, cursor navigation, source admission, and restart. The current keyword contract is positional search, so the obsolete entity-scoring algorithm is not preserved. |
| `test_query_hashes_and_parses_same_bytes` | `tests/test_native_source_header.py::test_header_checks_current_binding_installation_and_cancellation` owns immutable installed carrier identity admission; `tests/test_native_document_reader.py::test_exact_native_ranges_reuse_scalar_owner_and_keep_unicode_offsets` owns exact bounded canonical byte hydration. Aggregate JSON hash/parse is deleted, not replaced by another whole-file parser. |
| `test_retrieval_index_references_canonical_snapshot_without_copying_records` | `tests/test_native_build_worker.py::test_build_worker_returns_pending_native_publication_without_materialization` and `test_schema_does_not_offer_retired_aggregate_validation` own native publication handoff without aggregate carriers. `tests/test_native_query.py::test_actual_native_semantic_and_grounded_knowledge` verifies real canonical native records and located grounding. There is no retrieval-reference or snapshot artifact to retain. |
| `test_query_process_cache_reuses_admitted_bytes_and_rejects_file_changes` | `tests/test_native_query.py::test_actual_native_keyword_two_phase_hydration_and_reopen` verifies session close/reacquire behavior; `test_native_query_rejects_stale_receipt_and_source_binding` verifies current publication/source admission. The source-header installation test rejects file changes. Caching the complete snapshot once is a removed implementation requirement, not a user-visible invariant. |

## Validation

`.venv/bin/python -m pytest -q tests/test_kernel_owner_regressions.py
tests/test_native_query.py tests/test_native_vector_owner_audit.py
tests/test_native_keyword_owner.py tests/test_native_source_header.py
tests/test_native_document_reader.py tests/test_native_build_worker.py`:
67 passed in 7.71 seconds. Scoped `git diff --check` passes.

No G4 completion or packaged/real-ESG acceptance claim follows from this focused
test-owner cut. Upstream disposition remains pending; equivalent upstream
contracts should replace these fork tests only after rerunning the invariants.
