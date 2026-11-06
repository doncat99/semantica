# Stream grounding bodies through the existing evidence batch owner

## Native assessment and reason

Inspected dirty fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`.
The current native owners are `semantic_document_reader::_read_source_locations`,
`semantic_source_artifact::_NativeSourceLocations`, and
`semantic_artifact_builder::_extraction_context_batches` / `_extract_window`.
The native reader already selects complete structural closure through indexed
location addresses, including same-table, caption, note and reference closure.
The defect was in its consumer: `_window_grounding_context` hydrated every
closure quote into a list, and the batch owner then retained all model batches.
Reader paging alone therefore did not bound downstream body retention.

## Implemented change and affected callers

The existing source-location reader exposes the ordinal with unhydrated
location addresses. The source location adapter hydrates that exact immutable
ordinal through the same native reader, one record per read. Hydrated DTOs
retain their prior shape. No new stored bodies, secondary index, alternate
reader, or fallback has been introduced; existing indexes require no migration.

The grounding context now carries a repeatable native address selection. Its
batch owner retains at most 256 KiB of encoded address descriptors (the existing
native reader physical byte ceiling), and hydrates the current candidate and
indivisible evidence group only. Plans exceeding that metadata budget fail
locally with nonretryable `EXTRACTION_CONTEXT_BUDGET_EXCEEDED`, before any quote
reads. They are never truncated or reported complete. Individual scalar,
physical-read and request budgets remain unchanged.

Batches are yielded to `_extract_window` one at a time. The model-overhead
refinement path also keeps iterators rather than retaining all refined batch
bodies. Two bounded refined batches may be inspected to verify a real split.
Complete contexts fitting the request retain exact prior input ordering and
operation identity. Split contexts retain original refs/offsets and the existing
row/header/note/spanning-label semantics. Duplicate refs retain their individual
native record addresses.

The only production batch caller is `_extract_window`; direct regression
callers now explicitly collect batches only when comparing their complete
coverage. `semantic_extract` still receives one bounded list per request.
`_GroundingContext.__iter__` remains repeatable for structural evidence callers,
hydrating records incrementally from native addresses.

## Regression evidence

New red specification `test_context_planning_never_hydrates_the_complete_closure`
failed before the change because the existing consumer demanded hydrated context.
It now checks zero body reads during context creation, incomplete closure reads
when the first batch is emitted, bounded first request, and complete final ref
coverage. Additional regressions cover metadata-plan rejection before body reads,
oversized indivisible-row rejection before reading its tail, and address-by-address
hydration parity with the frozen independent native structural oracle.

Existing tests continue to cover exact small-context input, all rows/headers/
notes, spanning labels, local entity namespaces, interrupted paid-pass restore,
model-overhead refinement, explicit structural dependencies and native reference
handoff. Focused verification is recorded below after execution.

## Limits and upstream disposition

Large address closures above 256 KiB explicitly fail; this change does not claim
that arbitrary-size metadata planning is supported. The indexed reader remains
the correct owner for future storage-side row-group selection if that limit is
reached in real documents. Repeated header hydration trades extra bounded reads
for avoiding retained closure bodies. This patch does not close project-global
memory, other native persistence owners, full G4 acceptance, paid ESG builds,
release packaging or consumer artifact pins. Upstream merge assessment is pending;
preserve closure-fidelity and resource regressions when merging native readers.

Focused run after implementation (offline; no model/network calls):

```text
.venv/bin/python -m pytest -q tests/test_semantic_artifact_grounding_budget.py tests/test_native_source_locations.py tests/test_request_content_optimization.py tests/test_structural_fact_evidence.py tests/test_native_window_reference_handoff.py tests/test_native_document_reader.py tests/test_native_source_windows.py tests/test_native_source_admission_budget.py tests/test_native_producer_publication.py
75 passed in 14.64s
```
