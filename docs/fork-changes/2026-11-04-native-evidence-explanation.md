# Native evidence explanation and removal of duplicate report transport

Status: implemented; focused native worker verification recorded below. No real
ESG build, packaged App or model-backed product acceptance is claimed.

## Native owners and removed path

Inspected `semantic_worker.py`, `semantic_artifact_builder.py`,
`triplet_store/publication_records.py`, `semantic_document_reader.py`, and the
host `runtime.generateReadingReports` handoff. The host TS wiki compiler owns
reading-report generation. The unused Python `generate_reading_reports` method,
its request DTO and its whole-aggregate report loading are deleted.

`_verified_snapshot`, snapshot file/digest/id explanation inputs and builder
`explain_evidence(SemanticArtifact, ...)` are deleted. Their tests are replaced
by real native-store/reader tests, with no compatibility reader or graph adapter.
The existing `_grounded_explanation` and `CommunitySummarizer.summarize_evidence`
remain the single explanation computation owner.

## Current contract

`explain_evidence` receives `projectId`, `semanticStore` (absolute path, project,
generation), up to 32 `sources` (source/material/representation identity and
verified canonical source + reader-index references), up to 32 exact native
evidence IDs, `target` (id/type/title), existing `outputDir`, and model `relay`.
No source bodies are transferred or copied into worker inputs.

The worker checks ready publication and project, point-reads only selected
Evidence/Mention/IdentityProfile records and their linked NativeRange records,
then resolves each fact's source/material/representation through the publication
owner. `OxigraphStore.read_record_binding` delegates one membership join with
`LIMIT 2`, rejects missing/ambiguous bindings, and fences the current generation.
The caller's source artifact revisions must match that authoritative tuple.
Entity IDs cannot stand in for located evidence spans.

Only proven scalar ranges are hydrated using the existing source range reader.
NativeRange order, extent and proven newline separators are checked; no quote
search or serializer-content guessing is used. Context is transient, contains
only the selected evidence, and is never adopted as another fact collection.
Across an explanation the worker enforces 128 scalar ranges, 256 KiB total
charged record/physical-read/context bytes and a 30-second hydration budget;
over-budget requests fail explicitly before model generation, never truncate.
The native handle is closed on success and failure. Host orchestration must
release its acquired query handle before this worker opens the same Oxigraph
store, and hold the existing store-operation fence through the worker call.

The generated result file has `protocol`, `projectId`, `generation`, `target`,
generated `sections`, cited `evidenceIds` and `modelReceipts`. It contains no
source-body mirror or snapshot identity. Output is limited to 256 KiB. The
worker returns only its path/digest and section/receipt counts. Formal business
adoption remains with the host; this is not another report persistence owner.

Build responses now transparently transport the producer's required
`nativeIndexes`; they do not materialize aggregate artifacts.

## Verification and limitations

- Native explanation, worker, scalar-grounding and record-worker suites plus
  focused existing native explanation computation: **44 passed, 37 deselected**
  in 3.75 seconds. `git diff --check` passed.
- Broader native document-reader, explanation, build-worker, record-worker,
  scalar-grounding, publication-record and extraction-record regression:
  **72 passed** in 6.00 seconds.
- Tests use actual embedded Oxigraph and canonical reader artifacts, and verify
  joined scalar fidelity, source/revision/project/generation rejection, exact
  evidence types, stale installations, duplicate and overbroad selections,
  handle release and absence of source text in generated output.
- Broader pre-existing aggregate build tests still require producer/fixture
  migration; they are not evidence that this native contract is product-ready.
- Docling transformed table serializer spans without exact native-scalar proof
  remain unsupported; no approximate grounding is fabricated.
- Native owner extension only; no dependency changes or parallel engine. The
  worker protocol change is a breaking boundary migration, not an upstream API
  compatibility layer.
