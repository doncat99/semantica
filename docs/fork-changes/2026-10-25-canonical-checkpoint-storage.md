# Canonical completed-work storage and verified import

- Record ID: 2026-10-25-canonical-checkpoint-storage
- Date / author: 2026-10-25 / repository contributor
- Status: verified-in-stated-scope; source only
- Fork base revision: 5e6ea9af4d612c49bdaa3e4cedb35342010cd20b, canonical checkout on main
- Upstream reference: no incoming upstream revision reviewed
- Related issue / PR / commits / records: [earlier model-independent checkpoint record](2026-10-24-model-independent-checkpoints.md); publication pending

## Reason and scope

Completed work must outlive job directories and producer changes. The prior
review's repairs were split between a detached draft and the canonical build
checkout. This change consolidates the repairs in the actual native owner.
OntoScience's `engineering/scripts/dev-dependencies.ts::buildDevDependencies`
selects `~/Documents/external-sources/doncat99/semantica`, not the detached draft.
That checkout is source for an explicit artifact build, never a runtime fallback.

## Native capability assessment

- Existing owners: `semantica/project_checkpoint.py::SnapshotCheckpoint`,
  `semantic_artifact_builder.py::_source_windows`, `_ExtractionCheckpointBackend`,
  `_relay_json`, `semantic_source_artifact.py::build_source_artifact`.
- Callers/contracts: `semantic_worker.py` build entry, `SemanticArtifactBuildRequest`,
  project and standalone-source extraction; generic extraction cache remains owned
  by its existing provider cache module.
- Tests inspected: checkpoint compatibility, project restart, grounding budget,
  semantic artifact, native grounded source/extraction, long context and scheduling.
- Decision: repair the existing persistence/cache owners. No second extractor,
  migration-time model, or runtime legacy reader is introduced.

## Approach and actual changes

- `project_checkpoint.py`: canonical business inputs; optional durable directory;
  dataset lock; verified one-time import; manifest/key/payload/rejection validation;
  conflict preflight; fsynced staging, journal, archive and publication; interrupted
  migration recovery. Runtime reads only the canonical directory. Original import
  bytes are evidence, never a fallback. Atomic incomplete writes are not results.
- `semantic_artifact_schema.py`: absolute `checkpointDir` contract. The explicit
  resume directory field is import input only, not a reader chain.
- `semantic_artifact_builder.py`: content/business-context keys for nonembedding
  work; current producer selection applies to unfinished calls only; original
  receipts survive reuse. Missing durable context rejects before network. Preserve
  exact embedding-space isolation and completed-source missing-plan/result fences.
- `semantic_source_artifact.py`: remove historical input fallback. Parse reuse
  retains the existing content/actual-business-requirement owner.
- Canonical builder already lacked the detached draft's release-schema digest
  rejection. Preserve that behavior and test release change plus vector-only rebuild
  with no new generation. No duplicate digest gate is added.
- Opaque historical extraction hashes cannot establish business identity. Preserve
  the bytes and reject automatic recomputation; a hash's presence is not proof.
  Explicitly rejected invalid results may be replaced while retaining their evidence.
- Consumers: OntoScience supplies one content/requirements dataset path across jobs;
  per-job output artifacts remain separate. Fixtures now supply immutable revisions,
  actual source window text and the business-context keyword used by production.
- Network/dependency/cost: local fixtures and mock providers; no new dependency,
  paid model calls, user-profile migration, deletion or App lifecycle operation.
- Not implemented: universal reversal of opaque historical hashes, release artifact
  production/pinning/publication, packaged installation and real-profile acceptance.

## Verification and limitations

Command from canonical checkout, using the existing test interpreter in the sibling
draft's `.venv` (interpreter only; imports resolve this canonical source):

```text
/Users/huangdon/Documents/external-sources/doncat99/semantica-main-merge/.venv/bin/python -m pytest -q --tb=short tests/test_canonical_checkpoint_storage.py tests/test_checkpoint_compatibility.py tests/test_project_checkpoint.py tests/test_semantic_artifact_grounding_budget.py tests/test_semantic_artifact.py tests/test_native_grounded_source.py tests/test_semantic_artifact_native_extraction.py tests/test_semantic_artifact_long_context.py tests/test_semantic_artifact_scheduling.py
```

Result: **123 passed in 32.13s**. This includes worker process restart, cross-job
reuse, producer/prompt/release changes, vector-space separation, missing recovery
data refusing paid regeneration, import conflicts, journal/archive/publication
interruption, malformed journals and original evidence preservation. Supporting
evidence is in these test files and the task's command output.

Canonical fork `git diff --check` passed. Consumer focused tests passed 111 cases;
consumer workspace `typecheck` and `guard` passed (67 guard tests).

Initial expanded runs exposed stale mock signatures and impossible window fixtures;
the fixtures were corrected without removing production validation or weakening
the original ordering/concurrency/error-context assertions.

No immutable artifact, release pin, installed App or real-profile recovery is
verified by this result. Opaque historical keys remain explicit recovery gaps.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Likely conflicts: checkpoint persistence, project extraction cache, typed relay
  business context and schema/worker request fields.
- Retain one canonical native owner. Adapt or remove these repairs only when an
  upstream owner proves equivalent durable reuse, integrity and crash recovery.
- After merge rerun the command above plus consumer receipt/routing tests; packaged
  acceptance must use a newly built immutable artifact and an isolated profile.

## Dated follow-ups

- 2026-10-25: consolidated and verified in canonical main checkout. Earlier detached
  draft results remain historical; neither set of source tests establishes deployment.
- This consolidation record was written retrospectively during the final verification
  pass; the earlier record existed during implementation. This does not satisfy the
  record workflow's requirement to start a new coherent change record before coding.
- 2026-10-25: follow-up [project-local reuse](2026-10-25-project-local-reuse.md)
  corrects three omissions: whole-material-set directory routing, current-formula
  validation of historical v2 representation IDs, and display-name equality.
  The host now routes by project; native admits verified dependency-keyed entries
  and recovers whole relocated dataset transactions before canonical publication.
  Historical IDs remain digest-protected persisted identities; renames do not
  trigger parsing. New source verification is 151 passing tests and consumer
  verification is 114; the earlier 123/111 counts above remain historical.
  No new artifact, release pin, installed App or real-profile acceptance is implied.
