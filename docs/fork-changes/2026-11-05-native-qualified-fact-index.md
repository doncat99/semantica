# Native qualified fact reference index

## Reason and native owner assessment

Inspected dirty canonical fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`.
`ConflictDetector.qualified_fact_identity` and `reconcile_qualified_facts` own
identity and conflict decisions; `EntityMerger.merge_qualified_fact_group` owns
support merging. Publication and extraction records already own durable native
observations and pending-build membership. Existing owners had no reference-only
index joining complete conflict groups across build pages. The project-wide
reconciler retained all DTOs; publication fact membership describes output and
cannot identify pre-reconciliation conflicts.

## Implemented

`semantica/triplet_store/qualified_fact_index.py::QualifiedFactIndex` indexes only
native Relation references, observation IDs, current qualified identities and
partition digests in the pending publication's native graph. Input DTOs are
consumed row by row and never stored. Build is explicit, generation fenced,
cancellation aware, rejects duplicate/foreign/nonrelation observations, and seals
only after successful completion. Restart reuses the same native index.

Partitions contain all objects and polarities for a subject/predicate and equal
remaining qualifiers. Thus both native polarity and declared functional-value
rules and their corresponding relations remain complete within one partition.
The index does not implement a second conflict algorithm: it rereads bounded
reference pages and delegates every complete partition to the unchanged
`ConflictDetector.reconcile_qualified_facts` owner. Output ordering across
partitions follows native digest order; consumers needing overall order must use
native publication indexes rather than retain project results.

`iter_reconciled(read, functional_predicates=(), max_group_records=4096,
max_group_bytes=16777216)` enforces explicit count and encoded-input byte limits
before yielding any output from a partition. The caller's `read(ref, kind,
observation_id)` reopens current native data and canonical endpoint mapping.
Identity/partition drift fails; no prefix is published as a successful group.
The defaults are safety limits, not proven ESG capacity or a claim that arbitrary
large semantic groups fit. Large single groups explicitly require a budget
decision or a further native support-output protocol; no evidence is truncated.

## Regression evidence

New `tests/triplet_store/test_qualified_fact_index.py`: red missing-module
collection failure in `/tmp/g4-qualified-fact-index-red.log`; then 4 passed.
A 274-observation partition crosses multiple 128-reference pages, closes and
reopens the native store, and equals the existing complete reconciler oracle.
A separate 280-observation test covers two times, positive value disagreements,
negative polarity, retracted observations, exact supports/status/conflict IDs and
a one-shot functional-predicate iterable. Resource violations fail before the
first semantic yield; incomplete build, duplicate references, generation changes
and foreign membership fail explicitly.

Focused index + existing project fact identity + canonical publication suites:
11 passed (2026-11-05). Affected conflict/deduplication/build-cursor/publication/project-fact regressions:
210 passed, 31 subtests passed in 5.14s
(`/tmp/g4-qualified-fact-index-regressions.log`).

## Integration and limits

The builder consumer integration is owned by the parallel canonical-publication
change. This module alone does not remove project DTO collections or close G4.
No model call, paid ESG capacity run, dependency/pin change, packaged artifact or
release publication was performed. Current bounded partition reconciliation
retains one partition, including its required support observations; allocation
may exceed encoded input bytes by Python/merger overhead and must be included in
whole-process capacity evidence. Upstream merge assessment pending; preserve the
single native semantic reducer and reference-only index ownership when merging.
