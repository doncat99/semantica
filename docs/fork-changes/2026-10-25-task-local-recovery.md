# Bounded task-local recovery and build timing

- Record ID: 2026-10-25-task-local-recovery
- Date / author: 2026-10-25 / OntoScience engineering
- Status: implemented; local verification complete in the stated scope; not packaged
- Fork base revision: 2d20ba37d2ca1bd77e197322292081d005661a85 (dirty migration work preserved)
- Upstream reference: not inspected
- Related issue / PR / commits / records: publication pending

## Reason and scope

The packaged ESG build exhausted a transient extraction task and restarted the
whole build. Successful work was restored, but scheduling and progress restarted.
Repair task isolation, bounded retries, heartbeat and lossless wire compaction.
Do not change extraction windows, business keys, model choices or source data.

## Native capability assessment

- Owner: pipeline/parallelism_manager.py Task, _execute_task and bounded thread scheduler.
- Caller: semantic_artifact_builder.py _native_parallel_map and _extract_project_sources.
- Existing regressions: tests/pipeline/test_parallelism_manager_fail_fast.py,
  tests/test_semantic_artifact_scheduling.py and grounding-budget tests.
- Decision: repair native owners; no additional executor, extraction or cache owner.

## Approach and actual changes

Implemented in the existing native owners:

- `pipeline/parallelism_manager.py`: optional bounded task attempts, explicit
  transient classification, permanent-error exclusion and retry-after-aware delay.
- `semantic_artifact_builder.py`: extraction/embedding use two attempts; exhausted
  transient tasks preserve independent dispatch/checkpoints and fail the build
  without automatic whole-build retry. Retry counts, attempt/delay, phase start/
  elapsed time and a joined five-second heartbeat use the existing progress path.
  Source failure counts clear only for tasks actually retried.
- `semantic_extract/methods.py`: compact only wire JSON whitespace, retaining all
  source and grounding evidence. Business keys and extraction plans unchanged.
- Added `tests/test_artifact_task_recovery.py` and extended native grounding tests.
  Existing `tests/test_relay_checkpoint_failure.py` mock now accepts keyword args
  supplied by the pre-existing `business_context` migration change; its assertions
  and failure behavior are unchanged.

No migration or deletion. Pre-existing checkpoint/parsed-source migration work
was preserved. No model/network calls in regression tests.

## Verification and limitations

Red: tests/test_artifact_task_recovery.py has four failures on the inspected base.
Native Python environment: .venv-upstream-sync (local, not an App input).
Focused recovery/grounding suites: 24 passed, including both 8/16 thread bounds
and successful/failed heartbeat shutdown. Relay checkpoint failure test: 1 passed.
An initial broad run was 70 passed / 1 failed due to the mock keyword mismatch
above, corrected and verified separately. Final broad rerun: **73 passed** (six
third-party deprecation warnings), covering recovery, artifact scheduling,
parallelism fail-fast, structured grounding, grounding budget, checkpoint
compatibility, process-boundary checkpoint restoration and relay failure.
Real-provider 8/16 comparison, artifact packaging and deployment not yet verified.

### 2026-10-25 release preparation correction

Expanded native extraction tests exposed two stale assertions: parallel task
diagnostics now include attempts, and exhausted task retries must not enable a
whole-build replay. Updated those assertions, adding an exact two-call check
while retaining the upstream status/code checks. This aligns existing tests with
the bounded recovery contract above; no runtime behavior changed in this correction.
Combined native extraction, kernel-owner, task-recovery, checkpoint-upgrade and
parsed-source-upgrade suites: **84 passed**, consumer evidence
`.tmp/esg-publish-native-tests.log`.

## Upstream merge assessment

Pending: upstream not reviewed. Retain only until the native scheduler provides
equivalent bounded retries, failure isolation and progress contracts. Re-run task,
parallelism, checkpoint and grounding regressions after any merge.
