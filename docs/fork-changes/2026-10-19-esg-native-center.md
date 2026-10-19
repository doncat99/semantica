# ESG native persistent semantic center

- Record ID: 2026-10-19-esg-native-center
- Date / author: 2026-10-19 / Codex, authorized ESG maintainer task
- Status: planned; branch alignment verified, behavioral port pending
- Fork base revision: `899bc07e` (merge of governed `9fac58a4` into local `main`)
- Upstream reference: not inspected in this change; fork origin/main `9fac58a4`
- Related records: [branch consolidation](2026-10-19-branch-consolidation.md)

## Reason and scope

ESG requires durable, evidence-linked native semantic state for shared company
information and document processing. Development must use the governed fork
`main`; an older dirty feature checkout is preservation evidence, not the base
to deploy or copy wholesale.

## Native capability assessment

- Native owners: `GraphStore.commit_snapshot/read_snapshot`, backend snapshot
  storage, `semantic_artifact_builder`, `SnapshotCheckpoint`, `ContextRetriever`,
  `PolicyEngine`, `ConflictDetector`, `EntityMerger`, grounded extraction schemas
  and `OpenAIProvider.generate_typed`.
- Callers: ESG `semantica_capabilities_worker.py`, native company/document
  adapters; fork semantic-worker, extraction, checkpoint, artifact and identity
  tests. No old project-worker entry point is to be restored.
- Latest main already owns strict OpenAI output, relay checkpoint preservation,
  identity vetoes and source progress. Reuse those changes unchanged.
- Repair only missing durability, native observation append/withdraw, bounded
  context and closed grounded wire contracts. No second semantic/identity engine.

## Approach and actual changes

- Preserved local TypeDB commit `bd671778`; `git cherry origin/main main` marks
  it patch-equivalent to the already merged native TypeDB implementation.
- Merged origin/main without resetting either history. The resulting tracked
  tree was byte-identical to origin/main before this record was added.
- Port pending: reconcile older uncommitted changes against current owners;
  omit unrelated formula work, already merged fixes and retired entry points.
- PostgreSQL business authorization/budget and immutable originals remain ESG
  responsibilities. No paid model calls or production restart during alignment.

## Verification and limitations

- Fetch, clean-main status, patch equivalence and `git diff --stat origin/main`
  verified before port. Source checkout remains intact with its dirty files.
- Behavioral tests, installed-package checks and consumer deployment pending.
- Older migration/test receipts retain their original source hashes; they do
  not validate this governed main tree or semantic correctness.

## Upstream merge assessment

- Disposition: pending. Compare incoming native snapshot, checkpoint, extraction,
  context, conflict and policy owners before retaining these extensions.
- Re-run native and ESG consumer regression after any owner overlap; never
  restore old workers or duplicate algorithms as a compatibility path.

## Dated follow-ups

- 2026-10-19: governed-main alignment completed; no claim of production recovery.

### 2026-10-19 implementation and isolated verification

The earlier planned status describes the alignment checkpoint. The native port
is now implemented on governed `main`, based on `899bc07e`; no changes were made
in the preservation checkout and no retired project-worker was restored.

- `GraphStore`/`Neo4jStore`: durable immutable snapshot revisions with staged
  writes, readback sealing, compare-and-set head publication and bounded append
  retries. Tests use a dedicated Neo4j instance, including concurrent/replayed
  and interrupted writes; this is not an atomic PostgreSQL/Neo4j transaction.
- `EntityMerger` and `ConflictDetector`: reuse qualified support reconciliation,
  retain withdrawn support/history, detect functional conflicts within the same
  conditions, and avoid treating different periods as one contradictory value.
- `ContextRetriever`: exact scope/revision selection, qualified assertion groups,
  conflict closure and explicit byte/fact budgets; oversized context fails rather
  than silently truncating. `PolicyEngine` retains the actual versioned policy
  content rather than fabricated placeholders.
- `semantic_artifact_builder`: native grounded-source snapshots and shared
  assembly/reconciliation/extension; strict closed wire schemas and refusal/
  incomplete-response checks. Preserve failed model receipts and cached rejected
  responses. Existing OpenAI typed provider remains the protocol owner.
- `SnapshotCheckpoint`: common source initialization preserves current main's
  progress/checkpoint contract. Grounded extraction methods, schemas and native
  tests were updated together; no extra ESG identity call or alternate scorer.

Verification on 2026-10-19: Python 3.13, dedicated Neo4j at port 17687,
`tests/test_native_grounded_source.py`, `test_native_snapshot_append.py`,
`test_native_persistent_center.py`, `test_native_snapshot_context.py`,
`test_project_checkpoint.py`, `test_project_fact_identity.py`, `test_project_identity.py`,
`test_semantic_artifact.py`, `test_semantic_artifact_long_context.py`,
`test_semantic_artifact_native_extraction.py`, and `semantic_extract/` tests
`test_grounded_wire_contract.py`, `test_grounded_llm_extraction.py`,
`test_structured_grounding.py`: **150 passed, zero skipped, 41.49 seconds**.
ESG isolated consumer checks additionally passed 114 document authorization/
settlement cases and 37 capture/registry/permission/mapper cases; these do not
replace native regression or consumer release acceptance.

Remaining: qualified installed-wheel checks, real parser assets and paid semantic
acceptance, production migration/deployment, independent company adjudication,
real multi-hop and continuous operation. No paid model calls were made for these
tests. The old full-company migration receipt refers to its own owner hashes;
it is not reclassified as validation of this port.

Upstream disposition remains **pending**: compare upstream changes in these
same native owners before merge. Reuse incoming native equivalents and remove
obsolete overlap; do not preserve duplicate implementations as fallbacks.
