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
Published native binaries require rebuilding before the new budget is available.

## Upstream Merge Assessment

Pending. Inspect the same native scene owner and rerun scene/projection tests
on merge; remove this change if upstream provides the same contract.
