# Native build pipeline

- Date: 2026-10-29
- Status: implemented; focused native execution and recovery verified
- Inspected base: ea75129c5; upstream local reference 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0
- Native owner: pipeline/PipelineBuilder, ExecutionEngine, FailureHandler
- Consumers: build_semantic_artifacts, semantic_worker, native append builds

The builder currently imperatively runs the entire workflow. Native pipeline
already supports dependency ordering, arbitrary state, typed original step errors,
and configurable retry policies. Reuse those owners. Product handlers translate
and assemble artifact contracts, while actual parsing/extraction/resolution and
organization retain their established native owners. Do not wrap the whole build
in one step or add a second scheduler/checkpoint store.

Split preparation, parsed-input admission, extraction, source projection,
classification, identity, reconciliation, organization and publication into real
dependent steps. Disable outer retries: provider and content checkpoints own paid
retry/reuse semantics. Preserve original error types at the worker boundary.
Keep sequential execution so active checkpoint ContextVars stay in this thread.

Regression requirements: native stage graph is observed during actual builds;
failure prevents downstream publication and is not retried; existing cross-process
stage recovery and paid-result reuse remain valid. No provider calls or user data
mutation. Case capability-library-prepare, primary journey-library, delta keep;
pass criteria, hard gates and baseline unchanged. Full release remains unverified.

Evidence: both new specs failed before implementation (no native execution was
observed). After the change, stage/order/failure plus existing project-stage
restart tests: 11 passed. Native pipeline/resource suite: 78 passed. Broader
artifact/identity/append/typed/cold-worker selection: 90 passed, 2 failed. Both
failures reproduce with the pre-change HEAD orchestration loaded in memory:
one expects a single mention evidence span despite concurrent contextual evidence;
one expects one report transport call despite existing provider schema retries.
No acceptance claim for those failures; unrelated dirty changes were not staged.

Task-only builder delta +254/-205, net +49. The moved statements are not deleted
algorithms. Nine dependent handlers actually execute parsing admission,
extraction, projection/classification, identity/reconciliation, organization and
writing through ExecutionEngine; no old sequential call path remains. Existing
_project_stage uses the sole durable content checkpoint, not a pipeline mirror.
Publication and quality mapping remain product contract assembly. Current native
engine returns failure objects, so the adapter rethrows the recorded original
step error without constructing an alternative failure policy.

Upstream assessment: retain native execution semantics and zero outer retries
when merging; this is fork product workflow assembly, not an untouched upstream
pipeline template. Artifact pin, host acceptance and real ESG build not run.
