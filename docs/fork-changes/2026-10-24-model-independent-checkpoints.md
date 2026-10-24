# Model-independent completed knowledge checkpoints

- Record ID: 2026-10-24-model-independent-checkpoints
- Date / author: 2026-10-24 / repository contributor
- Status: implemented locally; publication pending
- Fork base revision: 5e6ea9af
- Upstream reference: local main inspected; upstream not reviewed
- Related issue / PR / commits / records: OntoScience Library interrupted extraction recovery; publication pending

## Reason and scope

Changing generation provider, model or token limits must not discard completed
knowledge work. Embedding retains exact binding/model isolation, including
same-dimension but incompatible spaces. Preserve original receipts; validate
actual content, business extraction requirements, stored structures and entry integrity.
Producer schema hashes, processing contracts and implementation versions are provenance,
not historical-content expiration rules.
Do not run paid models or mutate the running application's data.

## Native capability assessment

- Owners: `project_checkpoint.py::SnapshotCheckpoint`, `semantic_artifact_builder.py::_ExtractionCheckpointBackend`, `_relay_json`, `_extract_window_context`.
- Callers: native extraction methods and ExtractionCache; project artifact worker.
- Tests: `test_project_checkpoint.py`, `test_checkpoint_compatibility.py`, native worker tests.
- Decision: repair native persistence/cache policy; do not add a second extractor.
- Existing manifests and cache entries must remain readable with their original fences and receipts.

## Approach and actual changes

- Planned: separate completed-work compatibility from execution provenance; preserve stage-specific vector keys.
- Stored-data impact: legacy manifests remain immutable; verify entries against their originating manifests.
- Model/network/dependency/cost impact: local mock tests only; no new dependency.
- Planned but not implemented: publication and packaged deployment.

## Verification and limitations

- Regression commands/results will be appended after execution.
- Full release acceptance and live-user retries are not authorized by this change.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Likely conflicts: native checkpoint compatibility and extraction cache ownership.
- Retain only while native recovery requires these repairs; rerun checkpoint and worker regressions on merge.

## Dated follow-ups

- 2026-10-24: native ownership inspected before implementation; red specifications next.
- 2026-10-24: implemented normalized content/contract compatibility while preserving original manifest fences and receipts. Project extraction and generation relay keys exclude execution selection; verified legacy model-bound keys remain readable. Embedding keeps exact binding/model/payload keys. Rejection markers apply across legacy aliases.
- 2026-10-24: 17 focused tests passed (`tests/test_project_checkpoint.py` and `tests/test_checkpoint_compatibility.py`), including old-format quota recovery with a changed generation model, worker subprocess restart, same-dimension embedding model isolation, retained provenance, package-only changes, and incompatible recipe/schema/processing rejection. Tests use bundled Python 3.12 and installed pytest with mocked relay transport; no paid model calls or active App mutations.
- Publication, pinned release replacement, and live App acceptance remain pending. Source-runtime tests are supporting evidence, not packaged product acceptance.
- 2026-10-24 follow-up: the earlier recipe/schema/processing rejection policy above is superseded. Completed parsing survives parser, profile and implementation upgrades; completed source results, product JSON and grounded explanations have content/business-context keys. Actual Pydantic validation and original manifest fences/payload digests remain enforced. Original source window plans are now persisted for both project and standalone source recovery.
- 2026-10-24 follow-up: 37 focused tests passed: 36 across project checkpoints, checkpoint compatibility, grounded source and PDF ownership, plus the worker subprocess restart regression separately (97.79s). This includes changed generation model after interruption, changed chunk algorithm with a saved standalone plan, whole-project embedding-model replacement without new parsing or generation, real subprocess restart with durable parse/entity/receipt reuse, and changed source bytes rejected. The subprocess test allows 90s for cold imports and terminal shutdown and cleans up its own worker on timeout.
- Legacy limits: old opaque cache keys without recoverable model/parameter inputs and missing historical chunk plans cannot be universally reversed. Existing files must be preserved and these cases reported as compatibility gaps. No claim of recovering all historical caches or all paid work is made.
- 2026-10-24 second review correction: the host deleted successful run directories and the checkpoint baseline comparison prevented reuse after snapshot adoption. The host now retains completed work; native `SnapshotCheckpoint` excludes the final-diff baseline and source display names from paid-work compatibility, normalizes source-set business options, and skips verified but unrelated candidates without aborting matching history. Original manifest and payload integrity fences remain mandatory. Inspected native owners remain `SnapshotCheckpoint`, `_source_windows`, `_extract_project_sources` and `_relay_json`; repairs extend those owners, with no alternate extractor.
- 2026-10-24 second review correction: missing historical window plans are explicit recovery gaps rather than permission to run today's chunker. For an unchanged source with unchanged extraction requirements proven complete by the adopted snapshot, missing plans or extraction entries raise `COMPLETED_WORK_RECOVERY_GAP` before provider generation. A generation guard also protects project generation in a vector-only rebuild. Existing snapshots stay intact; this does not reconstruct data physically deleted by previous hosts. New business revisions may perform genuinely new work.
- Regression evidence for this correction: tests first reproduced successful-snapshot cache loss causing new generation, source rename losing its checkpoint, incompatible candidates aborting recovery, and missing window plans silently re-chunking. Added mocked end-to-end assertions for completed snapshot plus embedding replacement, absent whole checkpoint and absent paid entity entries with a surviving plan; generation call counts must remain unchanged and gap codes are checked. Final commands and counts are recorded below after completion.
- Release boundary: the earlier local dev artifact above predates these second-review corrections. No new formal immutable release, consumer pin update, App installation, paid model calls, live-user retry, data migration or GC is claimed. Rerun native build/acceptance before distributing these changes. Upstream merge assessment remains pending.
- Second-review verification completed: 39 focused tests passed across `test_checkpoint_compatibility.py`, `test_project_checkpoint.py`, `test_native_grounded_source.py`, `test_pdf_reader_ownership.py` excluding the subprocess restart; restart passed separately within the project-checkpoint batch; `test_semantic_artifact.py` passed all 36 tests after adapting its repeat-build fixture to supply the original checkpoint and assert no additional extraction calls. Total unique tests: 76, executed in overlapping batches with mocked relays. Typed gap-code assertions passed in the project-checkpoint batch. `git diff --check` passed. No packaged-build acceptance was rerun for these corrections.
- 2026-10-25 correction: the historical legacy-alias/candidate-reader approach above is superseded. Canonical main now verifies one-time imports into one durable reader; opaque model-bound keys are preserved as recovery gaps, never silently retried. Repairs are consolidated in the actual build-source checkout. See [canonical checkpoint storage](2026-10-25-canonical-checkpoint-storage.md) for exact ownership, 123 passing regressions and delivery limits.
