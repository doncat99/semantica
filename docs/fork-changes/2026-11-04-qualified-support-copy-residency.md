# Qualified support copy residency

- Record ID: 2026-11-04-qualified-support-copy-residency
- Date / author: 2026-11-04 / Codex
- Status: implemented for redundant internal copies only; G4 incomplete
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference / merge assessment: not inspected / pending
- Native owner: `deduplication/entity_merger.py::merge_qualified_facts`

## Native capability and field-level audit

`conflicts/conflict_detector.py::reconcile_qualified_facts` delegates canonical
assertion/relation merging to the native EntityMerger. It currently materializes
complete `KnowledgeAssertion.model_dump()` and `KnowledgeRelation.model_dump()`
lists before merging. Identity uses assertion subject/predicate/object/qualifiers
or relation source/type/target/qualifiers. EntityMerger groups all input records
by that identity; it selects a representative by the complete encoded record,
not by the identity tuple. Observation deduplication and deterministic ordering
also use the complete encoded observation, including metadata and audit bodies.

Status reduction reads every original observation's `status`. Evidence/support
IDs come from active originals (or all originals when all are retracted).
Output must retain every unique original observation and its metadata, including
withdrawn supports. Representative metadata and all other fields are preserved.
Thus a selector carrying only status/evidence IDs cannot replace the current
records without changing representative selection, duplicate identity, ordering
or audit output. No such selector, metadata truncation or second store is added.

`kg/entity_resolver.py::resolve_entities` delegates grouped entity merging to
EntityMerger; it does not own the builder's upstream full-context deep copies.
No context/profile evidence is removed and no identity rule changes here.

## Exact change

The selected representative previously deep-copied its complete existing
`metadata.support_observations` subtree and then discarded it when writing the
new canonical observations. Its remaining full fields and metadata are now
deep-copied without that overwritten subtree.

Observation traversal now deduplicates original references using the existing
complete encoded key first, then deep-copies each retained unique observation
once, in exactly the prior key order. Previously every repeated occurrence was
deep-copied before overwriting the same dictionary entry. Outputs remain
independent of input mutations; all audit bodies remain present. Full-record
representative comparison and encoding are unchanged.

## Red specification and verification

`tests/test_native_support_copy_residency.py` exercises accepted/retracted,
candidate/contradicted, all-retracted, mixed rejected/accepted and all-rejected
support sets. Each input includes repeated full observations and a representative
with existing observation metadata. Instrumented audit dictionaries count actual
native deep-copy visits, while assertions check canonical ID, exact status,
active/withdrawn evidence behavior, complete observation payloads and source/output
mutation isolation. Red: **5 failed in 0.21s**, solely on each unique observation
being deep-copied three times instead of once; all preceding status/evidence/audit
preservation assertions passed.

After the native change: `.venv/bin/python -m pytest -q
tests/test_native_support_copy_residency.py tests/test_project_fact_identity.py
tests/test_native_snapshot_context.py tests/test_native_conflict_relation_access.py
tests/deduplication/test_merge_selection_sources.py
tests/deduplication/test_deduplication.py
tests/deduplication/test_cluster_merge_coverage.py`: **114 passed in 1.63s**.
Existing provenance/reorder, repeat-reconciliation idempotence, functional facts
and support-withdrawal regressions are included.

## Remaining boundary

Complete input model dumps, grouped records, encoded observation keys and full
output audit observations remain resident. This removes redundant copies but
does not establish a bounded full fact reconciliation. Replacing model dumps
with a generic read-only Mapping is not sufficient: the current native JSON
encoder expects JSON dictionaries, and model dumping can normalize nested Any
values. A direct attribute view would not automatically preserve those input
semantics. A native reference/selector design must address complete-record
representative/dedup ordering and audit output before replacing the current
contract; no compatibility union or fallback is introduced here. No builder,
dependency pin, persisted state or release artifact is modified by this change.

## 2026-11-05 follow-up: consume and release complete groups

The same native owner now yields canonical groups in its existing sorted identity
order. It removes each consumed group from its grouping dictionary before
building that group's complete independent canonical output. The sole production
caller, `ConflictDetector.reconcile_qualified_facts`, supplies model dumps through
a generator and validates each yielded output immediately. The previous complete
raw-dump list and complete merged-dictionary result list no longer overlap the
entire Pydantic output list. All repository callers of `merge_qualified_facts`
were inspected (the conflict owner and the dedicated copy-residency test); the
test that needs a complete result now explicitly consumes the iterator.

Full-record JSON representative selection, full observation deduplication keys,
sorted output order, complete audit bodies, deep-copy independence, status
reduction and evidence selection are unchanged. No dictionary view over Pydantic
models, new store, fallback, candidate limit or truncation was introduced.

Added `test_qualified_fact_groups_release_dumped_inputs_as_outputs_are_consumed`:
eight independent tracked dumped groups verify lazy canonical output and weakref
release of each consumed input group before later outputs; output audit bodies
remain available. Before the change this failed because all eight output audit
copies were allocated before the first result could be consumed (**1 failed,
5 passed in 0.15s**). After the change, focused fact/support/conflict regressions:
**12 passed in 1.40s**. Affected conflicts, deduplication, native reduction and
fact/support suites: **222 passed, 31 subtests passed in 2.56s**.

A no-model `tracemalloc` comparison reconstructed only the previous eager merge
implementation from the current function and fed both implementations the same
256 independent assertions with 16,384 nested audit rows. Complete reconciled
outputs compared equal. Previous merge peak: **14,508,975 Python allocation
bytes**; current: **9,962,644 bytes**. Retained outputs were 9,886,856 and
9,872,520 bytes respectively. This comparison keeps the conflict caller's dump
generator in both arms, isolating group consumption; it is a focused allocation
measurement, not RSS, worst-case capacity, or the complete G4 envelope.

Remaining: initial grouping still retains all raw fact payloads and all identities,
a large individual group still needs its full encoded audit keys, and canonical
models retain required audit observations. The full source/global build resource
contract remains open. Upstream merge assessment remains pending; adapt a future
native iterator change only after identical ordering/audit and input-isolation
regressions pass. No persisted data, profile pin, release artifact or paid model
execution was changed.
