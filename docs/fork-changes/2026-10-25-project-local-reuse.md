# Project-local reuse and immutable representation identity

- Record ID: 2026-10-25-project-local-reuse
- Date / author: 2026-10-25 / Codex
- Status: implemented; source regressions verified; artifact/App delivery pending
- Fork base revision: 5e6ea9af4d612c49bdaa3e4cedb35342010cd20b
- Upstream reference: not inspected
- Related records: 2026-10-25-canonical-checkpoint-storage

## Reason and scope

Material-set routing loses partial/completed paid work when a project changes.
The v2 parsed-source reader also recomputes persisted representation identity
using today's producer algorithm and rejects display-only renames.

## Native capability assessment

- Existing owners: project_checkpoint.SnapshotCheckpoint, semantic_artifact_builder._source_windows,
  semantic_source_artifact._load_parsed_source and bind_parsed_source_artifact.
- Callers: semantic worker and project builder; existing checkpoint, artifact and source tests.
- Decision: repair native owners. No alternate reader, pipeline or runtime fallback.

## Approach and actual changes

- `SnapshotCheckpoint._import`: retain protocol/project/scope isolation and
  verify original manifest fences and payload/key digests. Merge native
  dependency-keyed entries across material-set changes within a project;
  reject unknown unscoped entries when business inputs differ. Preserve opaque
  historical extraction/prompt identity recovery errors.
- Persist source/revision/OCR extraction-origin markers so removing and later
  readding a source cannot lose the missing-paid-plan protection.
  `_source_windows` consults the source-local marker, not global extraction
  presence. All source plans are saved before any paid extraction starts.
- `_carrier_roots`: finish interrupted transactions in relocated whole datasets,
  expand their canonical checkpoint and nested imports, then admit verified
  entries once. Conflicts preserve both originals. Archived evidence never
  becomes a runtime candidate or fallback.
- `_load_parsed_source` and `bind_parsed_source_artifact`: accept digest-protected
  persisted v2 representation identities without recomputing them using today's
  producer formula. Verify source bytes/revision, MIME, OCR, document structure,
  and the original document source/name relation. Display-only renames do not
  expire results; a new binding is independently published, with original
  artifact bytes untouched.
- Host counterpart routes only by project, validates request business identity,
  and moves old material-set directories intact into project imports. Its
  upgrade revision 3 also covers profiles already at revision 2 with no old runs.
- No new dependency, real provider call, user-data migration or App lifecycle
  operation was required.

## Verification and limitations

New regressions first failed on historical representation identity, display-name
equality and whole-project business-input fences. Host routing regressions also
failed before the project-only path change.

Final command, from the canonical checkout (the sibling environment supplies
only the interpreter, never source or an App runtime input):

```text
/Users/huangdon/Documents/external-sources/doncat99/semantica-main-merge/.venv/bin/python -m pytest -q tests/test_project_local_reuse.py tests/test_canonical_checkpoint_storage.py tests/test_checkpoint_compatibility.py tests/test_project_checkpoint.py tests/test_semantic_artifact_grounding_budget.py tests/test_semantic_artifact.py tests/test_native_grounded_source.py tests/test_semantic_artifact_native_extraction.py tests/test_semantic_artifact_long_context.py tests/test_semantic_artifact_scheduling.py tests/test_semantic_worker_imports.py --tb=short
```

Result: **151 passed in 55.05s**, using temporary fixtures and mock relay.
Coverage includes current/historical producer × renamed/unchanged display name,
digest tampering, binder original-byte preservation, material add/remove/revision/
OCR changes, deletion/readdition recovery gaps, relocated journal/archive/publish
interruption, nested imports and conflicting containers. Sixteen build variants
cover complete/quota-failed first run × four material changes × same/switched
generation model; unchanged windows retain original receipts and are not paid
again, including a subsequent embedding-only rebuild.

The first expanded run had four fixture errors reading an omitted default
documentProcessing field; the fixture now reads the validated request default.
No production check was relaxed to resolve those failures.

Consumer: **114 tests passed** across five focused daemon suites;
workspace `guard` (67 tests) and `typecheck` passed. Both repositories'
`git diff --check` passed. Consumer Case `capability-library-prepare` primary
`journey-library` remains unrun/blocked; supporting evidence expanded, existing
pass criteria/hard gates/baseline unchanged.

No immutable artifact, exact release pin update, App launch/installation or
real-profile migration/recovery has been verified. Opaque historical identities
and unknown legacy formats remain explicit recovery gaps, with originals
preserved and automatic paid recomputation prohibited.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed. Native owners
  overlap in checkpoint admission and parsed-source representation validation.
- Incoming upstream revision: not reviewed.
- Retain invariants of paid-data reuse, digest validation and one canonical reader.
- After an upstream merge, rerun the command above plus consumer routing/upgrade
  suites. A source pass does not replace immutable artifact or App acceptance.

## Dated follow-ups

- 2026-10-25 follow-up (planned): repair formula requirement completion admission
  in native `_build_semantic_artifacts`, using verified checkpoint recipe
  provenance to compare per-source business requirements. Preserve that provenance
  through canonical checkpoint import; do not read archived evidence at runtime.
  Inspected base remains 5e6ea9af4d612c49bdaa3e4cedb35342010cd20b.
  Add enable/disable/retry and missing-paid-result regressions; source validation
  only, no App deployment or live data migration. Upstream merge status pending.

- 2026-10-25 follow-up (verified in source scope): both enable/disable red
  regressions reproduced `COMPLETED_WORK_RECOVERY_GAP` before the fix. Native
  `SnapshotCheckpoint._import` now retains full recipe provenance as immutable,
  digest-keyed canonical entries, including a one-time import from verified
  manifest provenance. `_build_semantic_artifacts` resolves the adopted lineage
  digest and compares formula requirements per source. This lookup recovers
  history; it does not make a recipe/code version a data-validity condition.
  Evidence archives are never queried. Missing or mismatched historical
  requirements and missing completed results still report recovery gaps.
  No schema fork, second extraction owner, provider call path or dependency added.

  Updated tests: `test_project_checkpoint` covers enable/disable, unchanged peer,
  completed retry, return to original requirements, vector-only reuse and missing
  paid results; `test_project_local_reuse` covers old manifest import, multiple
  later imports and provenance key/digest tampering. First broad run exposed the
  single-source API's string recipe; provenance indexing is now explicitly scoped
  to project checkpoints. Rerun **168 passed** across the prior eleven suites plus
  `test_pdf_reader_ownership` (41.69 seconds). PyMuPDF emitted five deprecation
  warnings; no paid model or external relay calls were made. `git diff --check`
  passed. Host five suites: **115 passed**; guard (67 tests) and workspace
  typecheck passed. An explicit host/native subprocess fixture also bound an
  original disabled parse under a new unreachable remote profile without
  reparsing or rewriting original provenance.

  No immutable release artifact/pin, App delivery or real-profile migration has
  been verified; no commit/push. Case `capability-library-prepare`, primary
  `journey-library`: supporting evidence update only, journey/change-verification
  unrun, pass criteria/hard gates/baseline unchanged. Upstream merge assessment
  remains pending; preserve canonical ownership and rerun these regressions on
  any overlapping checkpoint/builder merge.

- 2026-10-25: implemented and verified in canonical checkout at the recorded base.
  This record existed before source changes; it corrects the narrower material-set
  and historical-representation coverage of the preceding consolidation record.
