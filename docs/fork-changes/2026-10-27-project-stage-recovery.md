# Project computation progress and durable completed stages

- Record ID: 2026-10-27-project-stage-recovery
- Date / author: 2026-10-27 / Codex
- Status: verified-in-stated-scope; consumer deployment pending
- Fork base revision: fa7af6313242343efa6e46eacb708ea4e92a3c37
- Upstream reference: local origin/main ca6c9f1918ad05e2bbaa4922fb32f34e2a508bb9; no new upstream fetch in this follow-up
- Related records: 2026-10-27-identity-extension-necessity

## Reason and scope

Extraction/embedding progress stopped before project entity resolution, qualified fact reconciliation, and community organization. Completed local project computations were not durable across worker restart. This repair extends the existing builder and checkpoint; it does not replace native resolution or add paid model operations.

## Native capability assessment

- Existing owners: semantic_artifact_builder.py::_build_semantic_artifacts, _resolve_native_entities, _remap_identity_facts, reconcile_qualified_facts, _semantic_organization; project_checkpoint.py::SnapshotCheckpoint; semantic_worker.py progress transport.
- Actual callers: worker build_snapshot dispatch, App runSemanticaWorker/engine registry. Existing project identity/artifact/checkpoint suites cover these owners. PipelineBuilder/ExecutionEngine do not own the complete artifact DTO/provenance projection; their orchestration APIs are not substitutes for this builder.
- Decision: extend existing persistence and progress owners. Native EntityResolver, fact reconciler and CommunityDetector retain decision ownership.
- No parallel cache, state database, resolver, fallback pipeline or full-snapshot restore path is introduced. The earlier alias/identity-positive deletions remain deleted.

## Approach and actual changes

- `_project_progress` reports start, one-second heartbeat, completed/failed state, start timestamp and elapsed milliseconds through the current worker callback. Source projection, optional source classification, entity resolution, fact reconciliation, semantic organization and artifact writing get named stages. Percent stays at the existing embedding boundary (90), never increases by elapsed time, and is not a completion claim.
- `_project_stage` persists only validated completed results using SnapshotCheckpoint's atomic writes/content digests. The existing importer recognizes self-scoped project-stage entries when dataset business inputs change; lookup still requires matching complete stage inputs.
- Entity result dependencies: full source mentions and explicit identity property schema. Fact dependencies: project identity, canonical entities/remap and source facts/relations. Organization dependencies: canonical entities, reconciled facts/relations and located evidence. Model/provider/release/code identifiers are not validity keys.
- Saved payloads undergo current typed schema validation. Corrupt bytes or invalid saved schema fail visibly; no recompute fallback conceals invalid completed data. Actual input/policy changes select different stage keys.
- Native resolver mutates nested input metadata. Deep-copy its input rows so source mentions remain immutable and fresh/resumed change deltas match. A new red test reproduced the mutation before repair.
- App consumers add labels to existing Library copy, recognize active stages, and suppress obsolete extraction counters on project stages. No layout/styling system or protocol envelope changes.
- Model/network/dependency impact: no new calls, packages or paid work. Existing extraction, classification and embedding checkpoints remain their sole owners.
- Incomplete stages may run again after interruption; completed stages do not. Source projection and final file emission rerun against the current output directory. This is stage-boundary recovery, not a claim of resuming halfway through a native algorithm.

## Verification and limitations

- Initial red specs exposed missing restart recovery/progress helpers; source-mention immutability red spec exposed nested metadata mutation.
- `pytest -q -p no:cacheprovider tests/test_project_stages.py tests/test_project_identity.py tests/test_project_fact_identity.py tests/test_semantic_artifact.py tests/test_semantic_artifact_contract.py`: 87 passed before the additional invalid-saved-schema test.
- Final project-stage suite: 6 passed, including three new-process resumes with completed native functions forbidden, changed model/release provenance, content/policy misses, digest corruption rejection, valid-digest invalid-schema rejection, heartbeat and failure status.
- Expanded checkpoint/identity regression: 93 passed, 11 failed. Two require missing optional `fitz`; eight historical upgrade tests omit the existing required `max_bytes` argument; one historical projection-change test lacks the existing model-context capacity admission. Loading original HEAD builder/checkpoint source in memory reproduces the same nine upgrade failures (one other upgrade test passes). These baseline failures remain explicitly open; no admission weakening or paid-data migration was added to obtain green results.
- Consumer guard and full workspace typecheck passed. Worker forwarding regression: 64 passed. Library mainline Auto Test change-verification passed, run `f5d2946e-c369-4c1d-9cb3-68c66ff69a2e`, including compliance and cleanup. This uses an isolated test runtime, not a production ESG build or published artifact.
- New-process fixtures bypass paid extraction transport; existing checkpoint suites cover transport reuse. Tests do not establish production ESG runtime speed or release artifact correctness.
- Further App guard/typecheck, worker/UI regressions and Auto Test results are recorded in the consumer review document. No commit, push, artifact publication, dependency pin change, packaging or production Build performed.

## Upstream merge assessment

- Disposition: keep pending equivalent native builder progress/completed-stage persistence.
- Incoming upstream revision reviewed: not newly fetched.
- Likely overlaps: semantic builder, project checkpoint importer, native resolver mutation semantics. Keep immutable source DTOs even if native merging becomes nonmutating.
- Remove/adapt this integration if upstream supplies equivalent content-scoped results and progress; never stack another owner.
- Required checks: process restart/no-recompute, changed-input/policy misses, schema/digest rejection, provenance/change-delta identity, existing checkpoint tests, worker metadata forwarding and App stage labels.
