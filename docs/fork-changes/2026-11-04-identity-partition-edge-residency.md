# Native identity partition edge residency

- Record ID: 2026-11-04-identity-partition-edge-residency
- Date / author: 2026-11-04 / Codex
- Status: implemented; focused verification only, G4 remains incomplete
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected; merge assessment pending
- Related work: G4 native global algorithm resource remediation

## Native owner and change

`deduplication/duplicate_detector.py::_partition_contextual_group` already
retains native direct-edge adjacency. Its merge loop additionally materialized
and sorted every same-identity edge as a second complete list of tuples.
Iterate row indices in ascending order and sort only that row's forward
neighbors. This preserves the exact lexicographic edge order and all native
ambiguity, conflict, membership and score behavior. The redundant complete
edge tuple list is removed; adjacency, blocked pairs and output scores remain.
No candidate cap, reduced recall, altered algorithm or new persistence owner
is introduced. Native pair work and retained adjacency remain quadratic.

## Red specification and verification

`tests/test_native_identity_partition_residency.py` characterizes all 729
four-node graphs whose pairs are same, unknown or different. It checks every
pair call in original order and hashes complete output membership and scores.
The pre-change golden SHA256 is
`3f2cd3b61af0b2d65ce0ddc9dc01aed2fddfdf9516e7773e0b9a488cdb289b44`;
the changed implementation produces the identical value.

A dense 256-mention graph with one conflicting pair checks all 32,640 native
comparisons and measures each actual sorting allocation with `tracemalloc`.
The old complete edge sort allocated 2,024,160 bytes against a 262,144-byte
per-sort bookkeeping budget: **1 failed, 1 passed in 0.22s**. The budget
measures the removable sort allocation, not input admission or total resolver
memory. The changed loop passes it while preserving native empty-group output
for this ambiguity case.

Combined focused command:

```text
.venv/bin/python -m pytest -q tests/test_native_identity_partition_residency.py tests/test_native_identity_candidate_budget.py tests/kg/test_identity_review_regressions.py tests/kg/test_contextual_identity.py tests/kg/test_identity_scope_and_sense.py tests/kg/test_entity_resolver_exact.py tests/deduplication/test_native_resolution_veto.py tests/deduplication/test_identity_constraints.py tests/deduplication/test_merge_selection_sources.py tests/deduplication/test_deduplication.py tests/deduplication/test_cluster_merge_coverage.py
```

Result: **300 passed in 7.27s**. This is focused native identity evidence,
not full build, repository health, packaged artifact or ESG acceptance.

## Full-row resolver audit and capability gap

No changes are made to builder `_resolve_native_entities` or the resolver's
audit lifecycle. Removing its input `deepcopy` is unsafe: native
`MergeStrategy._merge_metadata` shallow-copies the outer metadata dictionary
but then extends nested lists and updates nested dictionaries in place. Those
containers otherwise belong to immutable source-mention evidence. Custom
property merge callbacks also need an explicit ownership contract. Python
`deepcopy` of plain strings returns the same strings, so this is mutable
container copying and continued body-reference residency, not duplicate
allocation of every context string's bytes.

`EntityMerger.merge_entity_group` consumes context, description evidence and
identity profiles to choose supported output fields, then appends a public
`MergeOperation` retaining `source_entities` to `merge_history`. Dropping
context/profile data before resolution changes identity or provenance;
clearing merge history changes the public audit contract. Neither is a safe
copy-only removal.

Concrete follow-up options require an explicit native owner decision:

1. Characterize immutable input/output ownership, nested metadata/property
   aliasing and custom callback behavior, then implement native copy-on-write
   mutation points so the builder can avoid a full mutable-container clone.
2. Define an operation-scoped native audit lifecycle with durable complete
   evidence references and on-demand audit reads before replacing full-row
   `source_entities` retention. Preserve complete audit identity and content;
   do not silently clear or truncate the existing contract.

Neither option alone removes full mention availability needed by the current
global resolver. Partition adjacency, conflict neighborhoods, scores and
review state still require a native bounded-resource design. A plain DSU
replacement cannot preserve the partition's direct-neighbor ambiguity rules.

## Upstream merge assessment

Pending. Preserve exact native output and pair-order characterization and the
sorting allocation regression when assessing the upstream implementation.
