# Address-only native build window scheduling

- Record ID: 2026-11-04-source-window-residency
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty checkout)
- Upstream reference: not inspected in this follow-up
- Related records: [native build body budget](2026-11-04-native-build-body-budget.md), [source range hydration](2026-11-04-source-range-hydration.md)

## Reason and native capability assessment

The existing `_source_windows` materialized every window's text and both extraction
and embedding queues retained those bodies. `ParallelismManager` bounded active
workers but did not bound retained queued body bytes. Inspected native owners:
`semantic_artifact_builder._text_windows`, `_extract_project_sources`,
`_assemble_source_results`, `pipeline.parallelism_manager.ParallelismManager`;
callers include deterministic `_build_source`, model source processing, and source
scheduling/body/embedding tests. Reuse the same splitter and scheduler; no second
splitter, executor, persisted source store, or recovery mechanism is introduced.

## Changes and deletion targets

`_SourceWindows` retains the existing source text plus address pairs, materializing
a slice only when indexed by an active operation or assembly iterator. Queued jobs
carry addresses only. Extraction and embedding request contents, order, operation
identity, warning progress, retry policy and complete coverage remain unchanged.
Embedding result assembly uses a generator instead of a complete list of bodies.
The old builder `_bbox`/`_docling_locations` implementations were removed in favor
of the identical projection relocated to `parse.document_reader` by the concurrent
native-reader change; consumers continue to use one function owner.

No storage schema or data migration, model/network call, new dependency, publication
pin, or formal project data is changed by this seam.

## Verification and limitations

- `pytest -q tests/test_native_build_body_budget.py tests/test_semantic_artifact_scheduling.py tests/test_native_embedding_residency.py tests/test_semantic_artifact_long_context.py`: 26 passed before the added lifetime probe/projection move.
- `pytest -q tests/test_native_build_body_budget.py tests/test_native_extraction_handoff.py tests/test_no_checkpoint_runtime.py tests/test_native_build_lifecycle.py tests/test_semantic_artifact_native_extraction.py tests/test_semantic_artifact_grounding_budget.py tests/test_native_source_windows.py`: 65 passed after the changes. Includes actual 80-window weak-reference lifetime measurement: no window bodies at either queued scheduler boundary, peak live extraction bodies at most requested parallelism, complete ordered tail coverage, and zero retained bodies afterward.
- Real paid-result failure/restart handoff, no-checkpoint, cancellation/lifecycle and grounding specs rerun in that group. No external models/network invoked by these controlled fixtures.
- Final scheduling/embedding/long-context/native publication/build-pipeline rerun: 31 passed. These groups overlap earlier evidence and must not be added as a unique test count. Focused diff whitespace check passed.
- `_load_parsed_source` still materializes the source JSON and canonical text;
  `_text_windows` also uses a chunker that may allocate transient source-sized
  intermediate lists. This change bounds queued window copies, not total source
  RSS. Native extraction results and structural contexts can still retain bodies
  within the source phase, and global entity context/profile/topology budgets remain
  unresolved. G4 remains incomplete; this is not fixed-artifact or ESG acceptance.

## Upstream merge assessment

Pending: incoming upstream has not been inspected. If native scheduling or chunker
APIs change, adapt this address-only access in the same owners and rerun the above
ordering, retry, lifetime and paid-handoff checks; never retain both implementations.

## 2026-11-04 actual native admission follow-up

The earlier full-JSON admission limitation above is superseded by
[native source builder cutover](2026-11-04-native-source-builder-cutover.md).
Source text, window addresses, source locations and scalar maps are now native
range-backed. Source occurrence/passages stream bounded reads, and actual 16 MiB
admission RSS is measured in an isolated process. The earlier scope limitation
about global result/context budgets still applies; G4 remains incomplete.
