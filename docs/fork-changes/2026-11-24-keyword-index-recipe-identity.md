# Native keyword index recipe participates in completed publication identity

- Record ID: 2026-11-24-keyword-index-recipe-identity
- Date / author: 2026-11-24 / OntoScience maintenance
- Status: verified-in-stated-scope
- Fork base revision: 395d20b25e47bc6b4334a4fac35258bac8308ee5
- Upstream reference: not inspected; this is a fork-owned native publication contract
- Related issue / PR / commits / records: pending

## Reason and scope

An installed native keyword index built before page geometry was added has a
`positions` table without `page`, `y`, or `x`. The current query selects those
columns and failed with `no such column: p.page`. The index producer changed its
recipe digest, but the completed semantic publication key did not include that
recipe, so the builder could return the older completed index as current.

The change will bind publication reuse to the native keyword index recipe and
make the native reader reject an index whose receipt or table schema does not
match the current owner. It will not add a legacy reader, add missing columns to
old files, or treat an older recipe as current.

## Native capability assessment

- Existing owner and inspected files/symbols: `GraphSearchIndex.publish_native_positions` and `GraphSearchIndex.open_native_positions` in `semantica/explorer/search_index.py`; completed-result identity in `_build_semantic_artifacts` in `semantica/semantic_publication_builder.py`; publication address owner `PublicationRecords.completed_publication`.
- Actual callers / config / exports / tests / recent removals checked: `semantic_query.py` opens and queries the native positions index; `_build_semantic_artifacts` reuses completed publications; `tests/test_native_keyword_owner.py` and `tests/test_native_build_pipeline.py` cover native index and publication lifecycle.
- Decision: repair native producer and publication reuse identity.
- Evidence no second implementation is introduced: the existing `GraphSearchIndex` remains the only keyword index producer and reader.

## Approach and actual changes

- Changed files and why: `semantica/explorer/search_index.py` now owns one current keyword-index recipe digest and rejects receipts or schemas that do not match it. `semantica/semantic_publication_builder.py` includes that digest in completed-publication identity, so an index format change cannot return an older completed index. `tests/test_native_keyword_owner.py` covers stale recipe and schema rejection. `tests/test_native_build_pipeline.py` covers index recipe identity. `tests/test_native_extraction_handoff.py` rebuilds after an index recipe change and asserts that the persisted model-call journal is unchanged.
- Contract / consumer / stored-data impact and migration or deletion targets: the next explicit build for unchanged inputs creates a new publication generation and native keyword index from the existing parsed-source reader. It does not mutate an old index file or add a compatibility reader. The existing native query owner continues to consume the single current index schema.
- Model / network / dependency / cost impact: the build regression used a local transport fixture. Across an index recipe change, the model-call journal did not change; no external model request or new dependency was introduced.
- Planned but not implemented: publish the updated Semantica artifact and advance OntoScience's exact immutable artifact pin; rebuild and validate the existing user profile's stale index.

## Verification and limitations

- Commands and results (include scope and evidence paths): `.venv/bin/pytest -q tests/test_native_keyword_owner.py tests/test_native_build_pipeline.py tests/test_native_extraction_handoff.py` — 38 passed, including a real native build whose index recipe changes; model-call journal remains byte-for-byte unchanged. `git diff --check` — passed.
- Checks not run and why: full Semantica test suite and packaged OntoScience validation not run; this local checkout is not yet published or pinned by OntoScience.
- Known risks / unresolved questions: current packaged artifacts and existing user indexes remain unchanged until the immutable Semantica artifact is published, pinned, packaged and explicitly rebuilt from saved parsed sources.

## Upstream merge assessment

- Disposition: pending; retain only while upstream lacks equivalent native index recipe identity and stale schema admission.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: upstream keyword index producer or publication completion protocol.
- Conditions to retain, adapt or remove this change: compare upstream index recipe, schema admission and completed publication identity before merge.
- Required consumer/regression checks after merge: native keyword owner and completed publication reuse tests; OntoScience host query and packaged data migration acceptance.

## Dated follow-ups

<Append verification and review results here.>
