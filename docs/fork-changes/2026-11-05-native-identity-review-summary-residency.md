# Stream exact native identity review summaries

## Native owner and reason

Inspected canonical dirty fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`.
The existing owner is `DuplicateDetector.iter_identity_review_summaries`; its
production caller is `semantic_artifact_builder._resolve_native_entities`.
Contextual candidate generation already streams and stores unknown decisions as
native bitsets. The summary consumer expanded all canonical candidate/reason
pairs into a Python tuple set before returning an exact count and only eight
examples. This allocation was unnecessary for the requested projection.

## Implemented change

Reuse the same bitsets and canonical remap. For each reason, deduplicate canonical
IDs, add their exact count, and stream candidate/reason tuples into `nsmallest(8)`
with the previous eight examples. Release the current ID set before yielding.
This preserves post-merge deduplication, exclusion of the mention's own canonical
entity, distinct reason counting, and the globally sorted eight examples.
No candidates are truncated from the exact count or identity decisions. No new
storage, dependency, policy, public export or alternate implementation is added.
The caller and published summary shape are unchanged; no data migration applies.

## Red specification and verification

`tests/test_native_identity_partition_residency.py::test_review_summary_does_not_materialize_every_candidate_reason_pair`
uses 8,192 mentions, two reasons and a many-to-one canonical remap. The complete
count and ordered examples already matched before the change, but summary
allocation was 988,816 bytes against a 524,288-byte complexity budget. The old
owner failed; the repaired owner passes. This budget measures the projection's
allocation and does not limit admitted entity count.

Affected suites: native partition residency, native candidate budget, identity
review regressions, contextual identity and identity constraints: **155 passed
in 5.31s** (`/tmp/g4-review-summary-green.log`). After explicit current-set release,
the new resource specification was rerun and passed; final merged rerun of the
same five suites: **155 passed in 6.95s** (`/tmp/g4-review-summary-final.log`). Red evidence is
`/tmp/g4-review-summary-red.log`.

## Limits and upstream disposition

The active canonical ID set still grows linearly with candidates for one reason;
compact unknown bitsets across all mentions and exact conflict partition can
still grow quadratically. This repair does not qualify the full identity stage
or G4's project resource envelope. It does not change model calls, artifact pins,
packaging or production data. Upstream merge assessment remains pending; preserve
the exact-count and residency specification when merging this native owner.
