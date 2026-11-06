# Native extraction window reference handoff

- Record ID: 2026-11-04-native-window-reference-handoff
- Date / author: 2026-11-04 / Codex implementation agent
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe; inspected dirty G4 worktree
- Upstream reference: not inspected
- Related record: [native streaming dispatch](2026-11-04-native-streaming-dispatch.md)

## Reason and scope

The scheduler already queued source addresses, but `_extract_window` combined all
split-context native Entity/Relation objects, and `_extract_project_sources`
retained every completed window until assembly. Paid extraction had already
accepted the same semantics into native Oxigraph, so these objects were a second
in-memory carrier. The red specification reproduced this retention before the
source change: the completed window was a materialized extraction dictionary.

## Native capability assessment

`semantic_extract.grounded_window.extract_grounded_window` already adopts accepted
extraction into `ExtractionRecords`. `OxigraphStore.read_extraction` and
`read_extraction_receipts` restore those records using full extraction binding,
current window text and native scalar ranges. Existing extraction and recovery
tests exercise these owners. Reuse these owners without another persistence
format, extractor, model path or semantic algorithm.

## Approach and actual changes

- `semantic_artifact_builder._extract_window` returns an immutable reference
  handoff containing extraction bindings, scalar addresses and specification
  instead of completed native entities and relations. Each context's semantic
  objects are released immediately after adoption.
- `_extract_project_sources` retains those references and the restored flag;
  temporary model receipt payloads are consumed for progress then released.
- `_iter_grounded_window_results` restores one accepted context at a time through
  the existing native owner. Existing batch occurrence namespace, relation
  endpoints, qualifiers, evidence, entity native refs and receipts are preserved.
- Empty entity extraction declares only its accepted entities operation: the
  grounded owner returns before relation generation/adoption. The previous
  builder reference to an unaccepted relations operation was incorrect.
- No stored-data migration, network/model request, dependency or release artifact
  changes. Standalone non-native extraction retains its existing contract.

## Verification and limitations

The regression `tests/test_native_window_reference_handoff.py` failed before the
fix at the materialized-dictionary assertion. Its real native fixture now proves
original Entity/Relation object collection, store close/reopen, restoration with
model construction prohibited, and exact split-context relation/qualifier/
evidence/native-ref/receipt fidelity. A scheduler boundary test also checks that
12 completed windows retain reference handoffs and no temporary receipt objects.

Focused verification includes that regression, native extraction, grounding
budget, scheduling, task recovery, native source body budget, long context,
request content optimization and native embedding residency suites. Initial
combined run after updating the empty-operation expectation: 73 passed in 16.20s.
Final combined run after the scheduler-lifetime specification: **74 passed in
16.07s**, using `.venv/bin/python -m pytest -q` with those nine test files.

This change bounds completed extraction object residency; it does not prove
whole-build G4 boundedness. Source DTO assembly and downstream global semantic
algorithms still require their own qualification. Reads continue to use the
existing bounded accepted-operation integrity and restore contracts; this is not
a claim that restoration performs only page-sized physical reads. No real ESG
build, packaged runtime or full-fork release acceptance was run for this seam.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision inspected.
- Likely overlap: artifact builder extraction/assembly and native extraction
  restoration contracts.
- Retain or adapt only while accepted native references remain the sole completed
  extraction carrier. Remove this handoff if an upstream canonical producer
  consumes accepted records directly.
- Required merge checks: reference lifetime, native reopen/no-generation,
  split-context fidelity, empty extraction and scheduling/recovery suites.
