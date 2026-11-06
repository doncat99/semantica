# Identity candidate residency red specification

- Record ID: 2026-11-04-identity-candidate-residency
- Date / author: 2026-11-04 / Codex
- Status: implemented and verified for transient candidate-object residency only
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected
- Related work: G4 native builder/global algorithm resource remediation

## Reason and native capability assessment

The current builder delegates identity decisions to
`kg/entity_resolver.py::EntityResolver.resolve_entities`, using the contextual
`deduplication/duplicate_detector.py::DuplicateDetector` owner. Its
`_contextual_candidates` retrieves by names, definitions and scoped identifiers;
this avoids unrelated pairs but still retains every merge-allowed candidate
within a repeated-name bucket. Group partition and merger compatibility checks
also inspect pairs. No alternative identity implementation is introduced.

Inspected caller: `semantic_artifact_builder.py::_resolve_native_entities`.
Existing tests include `tests/test_native_reduction_boundaries.py`; the new
dedicated regression isolates candidate object residency before later merging.

## Actual changes and desired contract

Added `tests/test_native_identity_candidate_budget.py`. Three offline corpora
contain 16, 32 and 64 independently located mentions of the same organization.
The real contextual owner decides every pair. Runtime weak-reference finalizers
measure simultaneously live `DuplicateCandidate` instances; the consumer retains
only normalized pair IDs and checks the complete combinations oracle, duplicate
emissions, and each `same` / merge-allowed decision before checking residency.

The desired complexity bound is at most one resident candidate object per input
mention while every admitted pair remains covered. It is a test of linear
transient pair-object residency, not a product admission cap or permission to
truncate candidates. The test accepts an iterable, allowing the existing owner
to stream candidates without creating a new public algorithm or API.

The native `_contextual_candidates` now yields each merge-allowed candidate
directly, in the existing order, and `_build_duplicate_groups` accepts its
iterable. No pair is dropped; decisions, review bitsets, conflict partition and
merger compatibility rules are unchanged. The only runtime caller consumes the
stream fully before partition and diagnostic use. No dependency, persisted data,
policy, model call or network behavior changed.

Streaming the first candidate stage alone does not prove that the
downstream duplicate groups, conflict graph, review bitsets or full builder are
bounded; those remain separate G4 requirements.

## Verification and limitations

- Expected red command: `.venv/bin/python -m pytest -q
  tests/test_native_identity_candidate_budget.py`.
- Current implementation retains n*(n-1)/2 simultaneous objects: 120, 496 and
  2016 for the three corpora. Full pair coverage and decisions are unchanged.
- Observed run: **3 failed in 1.17s**, all at the final peak-residency assertion.
  Complete pair coverage, pair uniqueness, every decision and zero candidate
  objects after consumption passed before each expected failure.
- After the owner change, the same command: **3 passed in 1.37s**.
- `.venv/bin/python -m pytest -q
  tests/kg/test_identity_review_regressions.py
  tests/deduplication/test_deduplication.py
  tests/deduplication/test_cluster_merge_coverage.py`: **163 passed in 3.00s**,
  including review reset, exact post-merge diagnostic counts and indirect
  conflict/compatible-subgroup preservation.
- `.venv/bin/python -m pytest -q tests/kg/test_contextual_identity.py
  tests/kg/test_identity_scope_and_sense.py tests/kg/test_entity_resolver_exact.py
  tests/deduplication/test_native_resolution_veto.py
  tests/deduplication/test_identity_constraints.py
  tests/deduplication/test_merge_selection_sources.py
  tests/test_native_identity_candidate_budget.py`: **131 passed in 1.55s**.
- Scoped `git diff --check` passed. These focused suites do not establish
  whole-repository health or a bounded full resolver/build.
- G4 remains incomplete; no immutable artifact or ESG acceptance is asserted.

## Upstream merge assessment

- Disposition: pending; incoming upstream not reviewed.
- Preserve full candidate/identity semantics during a future owner fix and
  rerun conflict-bridge, ambiguity, alias and identity provenance regressions.
