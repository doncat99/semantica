# Native extraction build-input pages

- Record ID: 2026-11-04-native-extraction-build-pages
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty working tree inspected)
- Upstream reference: not inspected
- Related issue / PR / commits / records: G4; native-extraction-accepted-handoff

## Reason and scope

Accepted extraction already persists typed native records, but recovery returns complete operation Entity/Relation objects and requires source text. Global build stages need bounded field reads without source hydration. This change adds that read capability in the existing owner; it does not claim builder/global algorithms have adopted it or that G4 is complete.

## Native capability assessment

- Existing owner inspected: `ExtractionRecords.operation_identity`, `receipt`, `read`, `write_entity`, `write_relation`, and `OxigraphStore` delegations.
- Existing consumers inspected: builder extraction adoption/recovery; publication's typed field read shape and publication pagination. Ready-publication reads cannot be used before global build completes.
- Decision: extend the current extraction owner, using the same project named graph, accepted operation identity, ownedRecord references and field codec. No second store, business payload or compatibility reader.

## Approach and actual changes

- `read_extraction_records(binding, stage, after=None, limit=128, fields=None, max_bytes=262144)` returns `{records, next_cursor}`. Records use the existing publication-style typed RDF field shape. Main entities/relations are selected with native graph/type/ownership filters, persisted position cursor, ordering and LIMIT.
- Cursors include the complete input-tuple-and-stage operation identity; foreign revision/source/project/stage cursors fail explicitly.
- `read_extraction_nodes(binding, stage, record_ids, fields=None, max_bytes=262144)` reads up to 128 owned nodes, including linked attributes, profiles and native evidence ranges. Foreign operation nodes fail. Fields are projected at quad lookup, not after a whole-record load.
- Response JSON has a hard byte budget; excess raises ProcessingError rather than silently dropping fields or results. Missing/corrupt accepted operations fail closed.
- Existing stored facts, operation digests and full-operation recovery semantics remain the single current storage contract; no data migration is needed. No model/network/dependency impact.
- Planned but not implemented here: builder cutover, project-wide operation enumeration, indexed identity/conflict grouping, removal of global working sets.

## Verification and limitations

- Red specification: `.venv/bin/python -m pytest -q tests/triplet_store/test_extraction_records.py -k build_input`: 3 failures, missing read_extraction_records.
- Final green: `.venv/bin/python -m pytest -q tests/triplet_store/test_extraction_records.py tests/triplet_store/test_publication_records.py`: 31 passed in 14.23 seconds; tracked Oxigraph delegation diff passes `git diff --check`.
- Final extraction suite: 9 passed; covers pagination/order/completeness, field projection, restart, cursor revision isolation, node ownership, hard byte/option rejection, relationship qualifiers/support/native evidence and corrupt-operation rejection.
- Accepted receipt integrity verification deliberately retains its existing single-operation bound: at most 8192 owned nodes, 32768 fact quads and 2 MiB fact bytes. Therefore page result size is 256 KiB but validation may read the full bounded operation; this is not a promise of page-only storage reads and is never a project traversal.
- These focused owner checks do not establish end-to-end build memory bounds or release readiness. Full App acceptance, model execution and package release checks not run for this owner-only change.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Likely overlap: extraction field codec and Oxigraph delegations. Reuse upstream's equivalent native capability if introduced; do not retain duplicate readers.
- Required after merge: extraction/publication regression suites and integrated build working-set/resource oracle.
