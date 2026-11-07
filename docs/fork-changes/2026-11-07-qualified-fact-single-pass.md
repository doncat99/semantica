# Single-pass qualified fact support reconciliation

- Record ID: 2026-11-07-qualified-fact-single-pass
- Date / author: 2026-11-07 / Codex
- Status: verified in focused source scope; packaged/runtime qualification pending
- Fork base revision: 919efd53791f910800cb0c2a923489de6d29822c
- Upstream reference: not inspected
- Related issue / PR / commits / records: current ESG G4 remediation

## Reason and scope

Fact reconciliation and downstream semantic organization omitted the existing immutable build scope, causing complete
source-operation plan validation on every fact fence. Each canonical relation
then traversed its complete partition again to recover support references.
Repair these two repeated traversals without changing accepted extraction,
semantic reconciliation, current running jobs or paid results.

## Native capability assessment

- Owners: PublicationRecords.build_scope and QualifiedFactIndex._reconcile_partition.
- Consumers: semantic_publication_builder.fact_reconciliation; canonical_page;
  test_qualified_fact_index and test_fact_projection. Repository-wide caller search
  found no other QualifiedFactIndex.fact_members consumer.
- Decision: repair existing native owners; retain ConflictDetector as reducer.
- No new storage, semantic algorithm, dependency or alternate implementation.

## Approach and actual changes

- Reuse build_scope at fact and organization stage boundaries, retaining keyed pending-generation
  fences and cancellation inside it, and complete validation at normal exit.
- Produce bounded support-reference plans while hydrating each partition once;
  remove the redundant fact_members reader and update every iterator consumer.
- Record actual indexed observations and completed partitions in existing progress.
- Stored-data impact: none; no migration or cleanup. Processing digest changes;
  immutable artifact delivery and audited paid-result rebind remain separate.
- Model / network / dependency / cost impact: no model calls or new dependencies.
- Planned but not implemented: live artifact replacement during an active job.

## Verification and limitations

- Red specifications: iterator must return support plans with exactly one read per
  observation; production builder must use the existing generation build scope.
- Final affected selection: `python3 -m pytest -q tests/triplet_store/test_qualified_fact_index.py tests/triplet_store/test_fact_projection.py tests/triplet_store/test_canonical_fact_publication.py tests/test_native_build_lifecycle.py` — 23 passed in 17.94s.
- Query-count specification: complete operation-plan validation occurs once at
  scope entry and once at exit for 280 indexed observations. Cross-page support
  specification verifies exactly one hydration per observation, unchanged oracle
  output and complete support membership/representative identity.
- Cancellation and generation replacement still fail closed and clear the scope.
- Acceptance Case `page-knowledge-deep-relationship-project`: keep; these native
  tests are supporting evidence, not its UI primary owner or change-verification.
- Full product acceptance and real-scale speedup are not inferred from unit tests.

## Upstream merge assessment

- Disposition: keep, pending upstream review; repairs native fork owners.
- Incoming upstream revision reviewed: not yet reviewed.
- Likely conflicts: qualified fact index and publication builder.
- Retain only while native reconciliation and immutable build fences exist.
- After merge: fact-index oracle, build lifecycle and projection regression suites.

## Dated follow-ups

- 2026-11-07: native-owner inspection and red specifications prepared.
- 2026-11-07: two initial red specs failed as expected; the downstream organization
  family consumer independently reproduced the same absent-scope defect before repair.
  First affected suite: 23 passed (18.90s), before the downstream scope repair.
- 2026-11-07: final affected selection passed after organization scope repair;
  existing active ESG job and its immutable artifact were not modified.
