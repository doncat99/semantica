# Publication membership indexed reads

Inspected revision: `5d3d59a2bff9baaccf076ccec5bdfffa4e9ccb5b`.

Native owner: `PublicationRecords.member` in `semantica/triplet_store/publication_records.py`.
Callers include projected build reads, entity hydration, candidate indexing and public publication reads. Existing cursor and publication tests cover these consumers.

The real ESG build spends CPU in native graph queries during entity resolution. The isolated 2,048-entity paging diagnostic attributes 93% of read time to queries, including one membership ASK per record. The exact share of live build time remains unmeasured.

Planned repair: traverse native reverse indexes from the requested owned record to its operation, source and current publication head. Preserve exact source selection, graph isolation and stale-generation fences; no new store, data mirror or schema. Regression rejects query execution for point membership and checks foreign/empty source selections. No offline migration is needed.

Validation: pending. This change alone does not qualify real build capacity or publication readiness.

Upstream assessment: pending; retain only while the native owner still performs the repeated join.

## Dated follow-up: 2026-11-07

- Record ID: 2026-11-07-publication-member-index
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope
- Fork base revision: `5d3d59a2bff9baaccf076ccec5bdfffa4e9ccb5b`
- Upstream reference: not inspected; local fork owner inspected
- Related issue / PR / commits / records: commit pending; KnowledgeHub G4

### Reason and scope

Repeated project-wide membership joins and record sorting dominate the isolated native build read path. Repair those reads without changing extraction, identity semantics or paid-result storage.

### Native capability assessment

- Existing owners: `PublicationRecords.member`, `PublicationRecords.build_page` and the existing Oxigraph reverse indexes.
- Callers checked: `read_build_records`, entity disambiguation preparation, candidate indexing and projected hydration. Existing publication/build/candidate/context regressions cover the boundary.
- Decision: repair native owners. No second store, cache or index is introduced.

### Approach and actual changes

- `publication_records.py`: reverse indexed point membership; page accepted extraction operations before querying operation-scoped records. Native record IRIs extend their operation IRI, preserving the existing global lexical order and opaque cursor contract.
- Cursor scope, source isolation, generation fences, byte/row limits and cancellation remain enforced. Invalid record namespaces fail explicitly.
- Updated `test_publication_records.py` instrumentation for keyed reverse reads; added membership, query shape and 130-operation paging/restart tests in `test_build_record_cursor.py`.
- No schema, stored-data migration, model calls, dependency or network changes. Per-operation reads retain the extraction owner's existing size limits. No algorithm/concurrency change planned in this patch.

### Verification and limitations

- Before fixes, new membership/query-shape specifications failed on the old ASK/project join.
- `pytest -q tests/triplet_store/test_build_record_cursor.py tests/triplet_store/test_publication_records.py tests/test_native_build_pipeline.py`: 47 passed in 21.16s before adding the 130-operation test.
- `pytest -q tests/triplet_store/test_build_record_cursor.py tests/triplet_store/test_identity_candidate_index.py tests/triplet_store/test_native_identity_context.py`: 28 passed in 15.88s, including the 130-operation restart/source-isolation test.
- Host scratch evidence `.tmp/g4-build-page-profile-result.json`: same isolated 8,192-entity store, identical complete sorted IDs, baseline 16.07155s / current 1.21919s; queries 8,260 / 258. Current ran second with warmer caches. This proves the isolated read-path improvement, not live ESG end-to-end capacity.
- Fixed-artifact qualification and real-build completion remain pending. No unrelated full regression repeated.

### Upstream merge assessment

- Disposition: keep pending upstream review; incoming upstream revision not reviewed.
- Likely overlap: publication membership and build cursor reads.
- Retain while upstream repeats the project join; adapt to any native cursor replacement that preserves complete ordering, source scope and restart safety.
- After merge rerun the publication/build/candidate/context regressions and installed-worker qualification.
