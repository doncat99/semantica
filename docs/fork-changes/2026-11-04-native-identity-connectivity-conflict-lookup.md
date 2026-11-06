# Native connectivity residency and qualified-conflict lookup

- Record ID: 2026-11-04-native-identity-connectivity-conflict-lookup
- Date / author: 2026-11-04 / Codex
- Status: implemented; focused verification only, G4 remains incomplete
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected; merge assessment pending
- Related work: G4 native global algorithm resource remediation

## Native capability and exact changes

`deduplication/duplicate_detector.py::is_group_compatible` consumes every
pair in fixed order, rejects a native blocking decision, then checks whether
the same-identity edges connect all mentions. This connectivity-only check
does not need a complete adjacency representation. Replace its adjacency and
DFS bookkeeping with disjoint-set connectivity, retaining exactly the same
pair calls, order, early rejection, decisions and empty/singleton behavior.
No early success skips subsequent conflict checks. Connectivity bookkeeping
is linear in input mentions. Pair work remains quadratic; no new time,
cancellation or admission policy is claimed.

`_partition_contextual_group` remains unchanged: its ambiguity, neighborhood
and conflict-subgroup semantics require direct-edge information. Unknown
review bitsets and exact post-merge summaries also remain unchanged.

`conflicts/conflict_detector.py::reconcile_qualified_facts` previously scanned
all canonical relations for every polarity-conflict group. Build an in-memory
index of existing canonical relation references by the exact string endpoint
and predicate tuple once; each group retrieves its relevant buckets. Group
members with the same key share one bucket traversal. Qualifier dictionaries
still use the original equality expression, without hashing or normalization;
relation IDs retain sorted ordering and each canonical relation is emitted
once. Neither model bodies nor support observations are copied into the index.
This is an internal, operation-local reference index in the current native
owner, not another persistence owner or identity/conflict implementation.

Unrelated source, builders, contracts, dependency pins, persisted data and
release artifacts are not changed by this work.

## Red specifications and evidence

- Added to `tests/test_native_identity_candidate_budget.py`: exhaustive 729
  four-mention same/unknown/different graphs compared with an independent
  connectivity oracle; pair-call order and first-block early return checked.
  Dense 256-mention coverage checks all 32,640 pairs and a linear bookkeeping
  allocation budget. Red: **1 failed, 4 passed in 1.75s**; old dense adjacency
  allocated 2,453,912 bytes, above the 262,144-byte bookkeeping budget.
  After source change: **5 passed in 1.38s**. Additional unknown blocker and
  empty/singleton tests then added.
- Added `tests/test_native_conflict_relation_access.py`: 8/16 separate polarity
  groups plus unrelated relation buckets, qualifier key reordering, full-scan
  reference membership, exact member status, no duplicate relation IDs, and
  observed native endpoint property reads. Red: **2 failed in 0.36s** only on
  repeated reads (400/1,568 reads for 24/48 relations); all full-reference
  membership and status assertions passed.
- Combined focused regression command: `.venv/bin/python -m pytest -q
  tests/test_native_conflict_relation_access.py
  tests/test_native_identity_candidate_budget.py tests/test_project_fact_identity.py
  tests/test_native_snapshot_context.py tests/kg/test_identity_review_regressions.py
  tests/deduplication/test_deduplication.py
  tests/deduplication/test_cluster_merge_coverage.py tests/kg/test_contextual_identity.py
  tests/kg/test_identity_scope_and_sense.py tests/kg/test_entity_resolver_exact.py
  tests/deduplication/test_native_resolution_veto.py
  tests/deduplication/test_identity_constraints.py
  tests/deduplication/test_merge_selection_sources.py`: **304 passed in 2.93s**.
  This predates the two extra trivial-group/unknown-blocker parameter cases.
- Final focused rerun after those additions: `.venv/bin/python -m pytest -q
  tests/test_native_identity_candidate_budget.py
  tests/test_native_conflict_relation_access.py`: **9 passed in 2.19s**.
  Scoped `git diff --check` passed.

## Remaining boundaries

No full resolver/build memory or production release acceptance is asserted.
Conflict partition adjacency/scores, unknown-review bitsets, entity body
copies, qualified-fact merge copies and global community algorithms still
need separate bounded-resource assessment. The relation reference index adds
linear reference memory and does not resolve the retained full fact/model
set. No limits, truncated candidates, fallback or replacement knowledge store
are introduced.

## Upstream merge assessment

Disposition pending: preserve native identity and conflict semantics, retain
the focused memory/read and reference-parity specifications, and assess the
incoming upstream owner before merging. No upstream patch was reviewed here.
