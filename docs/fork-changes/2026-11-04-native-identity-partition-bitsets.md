# Exact contextual identity partition with compact adjacency

- Record ID: 2026-11-04-native-identity-partition-bitsets
- Date / author: 2026-11-04 / Codex
- Status: verified in the focused native identity scope; G4 remains incomplete
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty working tree)
- Upstream reference: not inspected
- Related records: [candidate streaming](2026-11-04-identity-candidate-residency.md), [qualified support residency](2026-11-04-qualified-support-copy-residency.md)

## Reason and native assessment

Inspected `kg/entity_resolver.py::resolve_entities`, its contextual detector
configuration, `deduplication/duplicate_detector.py::_contextual_candidates`,
`_build_duplicate_groups`, `_partition_contextual_group`, `is_group_compatible`
and `iter_identity_review_summaries`, and
`normalize/entity_normalizer.py::EntityDisambiguator.prepare`. The native owner
already streams candidate objects and records unknown reviews as bitsets.
Contextual conflict partition still built a Python set of neighbor indices per
mention and tuple objects for blockers. Complete candidate coverage therefore
retained quadratic Python objects even after candidate streaming.

The actual contextual resolver invokes the native partition through
`detect_duplicate_groups`; no new decision policy or storage owner is needed.
Existing exact semantics are characterized over all 729 labelled four-node
same/unknown/different graphs in
`tests/test_native_identity_partition_residency.py`. The original scoped-sort
allocation regression checked only a temporary sorted list and could miss the
much larger pre-existing adjacency allocation.

## Actual change

Repair `_partition_contextual_group` in place: represent compatible adjacency,
blocked adjacency, ambiguity and membership as integer bitsets. Iterate low bits
in increasing order to preserve the exact original lexicographic edge order.
Symmetric blocker rows preserve both endpoint orientations in membership tests.
Every original pair is still compared; unknown and contextual blockers retain
existing semantics. Return the same ordered groups and dictionary score payloads.
No candidate cap, alternate algorithm, external dependency, model/network call,
public protocol change, persisted-data migration or compatibility path is added.

## Red specification and verification

New regression `test_dense_conflict_partition_bounds_internal_pair_residency`
measures the complete native partition's allocation, rather than only sorting.
It checks all 32,640 pairs at 256 mentions and an empty result where intermediaries
are directly supported by both contradictory endpoints. Before source repair:
**1 failed, 2 deselected**, peak **2,180,984 bytes** against 196,608-byte regression
budget. This budget is an internal allocation regression, not input admission or
a claimed supported project size. After source repair a standalone repetition
measured **26,264 bytes** with the same input and complete pair coverage.

`.venv/bin/python -m pytest -q tests/test_native_identity_partition_residency.py tests/test_native_identity_candidate_budget.py tests/kg/test_contextual_identity.py tests/kg/test_identity_scope_and_sense.py tests/kg/test_identity_review_regressions.py --disable-warnings`:
**140 passed in 6.15s**. This includes the unchanged complete 729-graph golden
characterization, exact connectivity oracle and unknown-review regressions.

## Remaining native gaps

This repairs Python object growth; exact decision comparison CPU and retained
bits remain quadratic. The resolver still receives a full entity/profile corpus,
`EntityDisambiguator.prepare` builds project-global definition/context indexes,
and materialized partition outputs retain required score dictionaries. No claim
of globally bounded identity resolution or G4 completion follows from this test.

Also inspected `conflicts/conflict_detector.py::reconcile_qualified_facts` and
`EntityMerger.merge_qualified_facts`. They require full model dumps and grouped
records; representative ordering and observation deduplication use full JSON,
including metadata. All audit observations survive in returned DTOs. The current
native contract has no indexed fact-selector/observation-reference interface.
Replacing dictionaries by a generic model view or removing evidence/context
would change serialization or semantic/audit behavior. A complete persisted
working-set remedy needs selectors in the existing native store for canonical
fact identity and exact full-record ordering, batch observation hydration, and
consumers that publish persisted result references instead of a full DTO corpus.
That cross-owner change is not implemented by this focused partition repair.

## Upstream merge assessment

Pending; no incoming upstream revision reviewed. Retain/adapt only if upstream
still uses this partition owner. Re-run the golden partition characterization,
full identity regressions and complete allocation measurement after any merge.

### 2026-11-05 broader native verification

`.venv/bin/python -m pytest -q tests/test_native_identity_partition_residency.py tests/test_native_identity_candidate_budget.py tests/kg tests/deduplication/test_identity_constraints.py tests/deduplication/test_cluster_merge_coverage.py --disable-warnings`:
**965 passed, 35 skipped, 6 warnings, 5 subtests passed in 7.82s**. Skipped tests
remain skipped, and this result does not qualify cross-repository packaging,
real ESG acceptance or globally bounded identity/fact reconciliation.
