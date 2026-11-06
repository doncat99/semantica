# Native build resident-body red specifications and owner cuts

- Record ID: 2026-11-04-native-build-body-budget
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope (two red specifications only; production repair planned)
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe, dirty main worktree
- Upstream reference: not inspected
- Related records: native-document-reader, native-document-range-capability-audit,
  native-scalar-grounding, native-reference-publication, vector-link-incremental-publication

## Reason and scope

Maintenance may legitimately traverse the complete authorized project. The defect
is simultaneous retention of all parsed documents, projected text, sliced windows,
results and vector floats, not traversal itself. The current peak scales with the
whole project, not only one source. SourceBuildInput and build sources have no
source/artifact byte admission budget. A per-window model limit does not bound
the complete producer heap or interrupt an individual read_bytes/json.loads.

This change adds executable red specifications and this implementation plan only.
It does not change production, install dependencies, call models/network, publish,
alter source bytes or clean unrelated worktree changes.

## Native capability assessment

- `semantic_source_artifact.py::_load_parsed_source`: validates immutable identities
  but hashes source/artifact, reads the whole representation and json.loads it;
  `_native_text` projects a full string. Docling projection joins all scalars.
- `semantic_artifact_builder.py::_build_semantic_artifacts`: parsed_inputs retains
  every loaded tuple in parsed_sources through global stages. source_projection
  retains source_builds, including document/text, passages and model results.
- `_extract_project_sources`: materializes windows, locations, scalar_ranges,
  jobs and extracted/embedded arrays for all sources. `_assemble_source_results`
  retains embedding values as Python floats even on reuse.
- `semantic_document_reader.py::read_document_reader`: current canonical body
  range owner, chunks/pages/ranges selection, maximum 128 items; physical body
  reads at most min(selection.maxBytes, 256 KiB), 2 MiB SQLite cache, 30 second
  per-call execution limit, row/scalar cancellation and SQLite progress handler,
  immutable installation/header/digest/representation checks, readBytes receipts.
  There is no current iter_text API. A private iterator must delegate to this
  owner, not build a second reader/content store.
- `parse/document_reader.py::project_document_reader` can emit address records
  through a sink, but still receives a loaded document. It alone does not fix
  source loading. native_scalar_projection retains lists and full joined text.
- `tests/test_native_document_range_audit.py::_CLOSURE_PROCESS` demonstrates sparse
  structured closure with native Docling models and original references. This is
  test-only capability evidence, NOT a production structured-reader API.
- Native facts: `ExtractionRecords`/OxigraphStore adoption and receipt/read owners;
  publication_records owns bounded current-generation records and references.
  Current read_publication_records is generation-fenced: do not pretend it can
  read a not-yet-staged generation, or publish early to obtain an iterator.
  Extend the existing extraction/store owner with scoped staged-operation pages
  if needed; do not mirror facts in another database or JSON aggregate.
- Existing tests inspected: native_build_pipeline, native_producer_publication,
  native_extraction_handoff, native_document_reader, native_document_range_audit,
  native_scalar_grounding, native_semantic_field_fidelity_audit, native_embedding_builder.

Decision: repair the current producer and extend the existing native reader/store
owners where required. No second parser, extractor, reconciliation/identity owner,
community algorithm, business-value store or snapshot is justified.

## Approach and actual changes

Added `tests/test_native_build_body_budget.py`:

1. Four real parsed sources, real deterministic build and publication. A dict
   subclass wraps each real loader document; weak references measure its lifetime
   at real semantic organization. Expected zero loaded documents; observed four.
   The probe itself holds no strong reference to documents.
2. Four real parsed sources through the model pipeline, real window construction,
   stop at the scheduler before transport. Weak references measure live window
   lists and actual UTF-8 body bytes. Expected at most one materialized source
   window list; observed four lists, eight jobs, 92,196 body bytes.

These are initial structural resource contracts, not RSS limits or a complete
single-source bound. They must not become the only acceptance evidence. A window
generator could pass the container probe while still holding a giant string;
physical reads, RSS scaling, cancellation and field fidelity remain required.

### Disjoint, sequential implementation cuts (planned, not implemented)

1. **Reader/admission owner:** semantic_source_artifact.py and
   semantic_document_reader.py. Replace whole-body build loading with an admitted
   descriptor and delegated cursor iterator. Preserve every current immutable
   material, parser, processing profile, OCR, representation and quality check.
   Reader header currently does not replace all document-quality metadata; extend
   its existing metadata projection with explicit byte bounds if needed. Chunk
   hashing with cancellation; identity checks must fence each operation. Bound
   individual metadata/scalars, bytes in flight and retained overlap; typed budget
   failure, never truncate or silently drop a required range.
2. **Window/scheduler owner:** builder source-loading/extraction portion. Consume
   descriptor/pages, stable source/global offsets and scalar mappings in a bounded
   queue. Avoid all-project windows/jobs/results arrays. Reuse native extraction
   and accepted handoff; persist each successful operation before releasing its
   body. Preserve parallelism ceiling, retries, receipts, progress, no repayment
   on restart and atomic publication behavior. Do not invent source-part siblings
   or change paid-operation identity merely to get a passing memory test.
3. **Source projection/store owner:** builder projection/classification portion,
   extraction_records and native vector metadata access as needed. Read accepted
   native operation results in pages and retain only IDs/bindings/reference counts
   beyond each bounded batch. Materialize quotes only on demand for extraction,
   classification and reports. Avoid reading all cached vector floats merely to
   republish their range references. Preserve integrity checks with the native
   owner; a metadata shortcut must not accept damaged adopted payloads.
4. **Global algorithms:** separate follow-up cut, not mixed into body streaming.
   Load minimal ID/edge topology and explicitly bounded identity/fact groups from
   native owners. Keep necessary global semantics described below. Gate unsupported
   scale explicitly instead of claiming cursor pages make all algorithms bounded.
5. **Publication:** keep one current owner and atomically activate only after all
   source/canonical/community/topic/index receipts qualify. Generation references
   may be rewritten during bounded maintenance; that is not a vector/body rewrite.
   Delete obsolete full-project body/results carriers in the same delivery.

Each cut must update all immediate callers before handoff. Cuts 1-3 share builder
code and are sequential owner work, not permission for parallel conflicting edits.
This child exclusively owns the new tests/record; the parent owns production.

### Field fidelity required before replacing loaded document with pages

- Unicode/code-point offsets, nativeRef, start/end, window/global coordinate
  translation and deterministic ordering. Reader ordinals are not source offsets.
  Projection-inserted separators need the same scalar-proof treatment; never find
  repeated text by quote or fabricate evidence for synthetic whitespace gaps.
- Source/representation/material/recipe/model/parser/specification bindings,
  origin, parserVersion, MIME, quality/OCR and document processing identity.
- Page number/box, section path, Docling labels/provenance, repeated text addresses,
  table row/column spans and headers, parent/container references, captions,
  footnotes, rich-cell child references, formulas and picture OCR context.
  Chunk text+locator alone is not evidence all these fields survive.
- Preserve structural extraction context and supporting_refs; use bounded native
  structure closure in the existing reader owner. Never rescan whole JSON to fetch
  one parent/table, follow unbounded siblings, or convert a test probe into an
  unreviewed alternate production reader.
- Preserve passages/classification citation IDs, profile dimensional cardinality,
  qualifiers (typed value/unit/time/condition/polarity), occurrence IDs, evidence
  ranges, relation endpoints, merge field provenance and source withdrawal.
- Preserve complete report input admission: one chosen support per fact/source,
  all required structural supports and at least one passage for an otherwise
  uncovered source. Do not solve report memory by dropping inputs or changing its
  input digest/recipe without explicit contract treatment.

### Global-scope algorithms: what pages can and cannot solve

- `_resolve_native_entities` deepcopies full mention rows and calls the existing
  list-oriented EntityResolver contextual resolution. Candidate admission and
  transitive supported identity need project scope. Native candidate-key lookup,
  group-scoped reads and persisted selections can remove repeated body retention;
  naïve independent page merges change identity semantics. Current list API is
  not an implemented out-of-core resolver. Preserve review summaries, negative
  constraints, merged-field sources and complete candidate recall.
- `ConflictDetector.reconcile_qualified_facts` and EntityMerger group all assertions/
  relations by qualified identity, then derive polarity conflicts. These can be
  supplied by native indexed/sorted complete-key groups and persisted selections,
  reusing the same decisions. Group size itself needs a byte/time budget. Do not
  implement a competing SQL conflict engine or weaken support provenance.
- `_semantic_organization` builds canonical relationships and invokes native
  CommunityDetector greedy_modularity. It creates a full NetworkX graph. The
  algorithm requires project topology (IDs, edges, isolated nodes), not all source
  bodies, descriptions/quotes or vector floats. Stream topology into that owner
  only after source-body release; preserve relation IDs and canonical membership.
  Current NetworkX greedy call has no cooperative cancellation or graph budget.
  Budget/preflight plus existing worker process cancellation needs proof. Independent
  per-page communities, a different algorithm or silent truncation is incorrect.
- `_explanation_reports` currently constructs global entity/evidence indexes and
  filters fact lists before `_reading_report_context`. Native field projections
  and selected support/range lookups can avoid unrelated content. Full overview
  maintenance still needs all qualified facts under its existing admission policy;
  the present context lists remain a separate resource gap. `_grounded_topics`
  additionally builds evidence-to-entity/assertion indexes; use native references.

## Verification and limitations

- `.venv/bin/python -m pytest -q tests/test_native_build_body_budget.py`:
  **2 failed in 1.14s**, both target resource assertions above. No xfail, skip,
  transport or paid model calls. Initial large deterministic fixture hit an
  unrelated atomic extraction budget; reduced fixture and reran, obtaining the
  intended lifetime assertion. The model fixture still uses larger real windows.
- Production repair, full test suite, RSS scaling and real IPC cancellation not
  implemented/run in this change. These red tests intentionally make that gap
  visible; they do not establish G4/G5 acceptance.
- `.venv/bin/python -m pytest -q tests/test_native_build_pipeline.py tests/test_native_document_reader.py tests/test_native_scalar_grounding.py`:
  **32 passed in 6.76s**. Existing pipeline/reader/scalar behavior remains green;
  this is supporting evidence and does not resolve the two new red contracts.
- Follow-up acceptance: child-process 1/4/16-source and giant-single-source scaling
  with physical read-byte, peak RSS and retained body-byte observations; cancelled
  hash/read/window/staging work leaves active generation untouched and resumable;
  existing scalar/structure/fidelity suites; two actual same-input increment cycles
  with SQL/native-write instrumentation prove zero unchanged body/vector writes
  and zero new model calls, plus source removal, recipe change and failure cases.
  Value equality and warm OS page-cache reads alone do not prove these claims.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Likely conflicts: semantic producer/pipeline and reader/extraction native owners.
- Retain these contracts until equivalent runtime body/resource evidence exists;
  adapt probes when owner interfaces change, preserving observable guarantees.
  Never keep superseded executable paths to satisfy the old probe shape.
- Required checks after merge: producer red specs, native pipeline/handoff,
  scalar/structure/fidelity, physical budget/cancellation and increment acceptance.

## Dated follow-ups

- 2026-11-04: Tests and plan only. Production remains unchanged by this author.

### 2026-11-04 source-lifetime implementation (subsequent authorized scope)

The earlier red observations and plan above remain the pre-fix evidence. The
source-lifetime cut is now implemented, without claiming page-based build loading:

- `_build_semantic_artifacts` replaces parsed_inputs/extraction with a real
  source_processing pipeline stage. Each source is loaded, extracted, projected
  and its scalar address metadata computed before document/text/source_locations
  are removed and loaded locals released. source_projection then gathers the
  semantic values for existing global owners. Native pipeline ordering/failure
  handling remains real, not a renamed no-op. Pipeline stage test updated.
- `_publish_native_topics` now requires native_scalar_ranges and clips those
  original scalar addresses. Missing addresses fail closed; it never reloads or
  reconstructs a full document/text to map a topic citation. Its fixture now uses
  address-only input and covers missing-address rejection.
- Source-local progress is mapped into the overall 2..90 processing interval;
  sourceOrdinal/sourceCount explicitly identify its scope. Existing source/window
  statistics, receipts and errors come from the native scheduler unchanged.
- Lifetime test additionally rejects a new source load while the previous loaded
  document survives, and asserts published source dictionaries have no full-body
  keys. Model scheduling test is unchanged in its resource expectation. A new
  barrier test verifies one source still executes windows concurrently with the
  requested two-worker budget and retains every window in source order.
- Changed production: semantic_artifact_builder.py only. Changed supporting tests:
  native_build_body_budget, native_build_pipeline, native_producer_publication.
  No stored-data migration, new storage, dependency or transport is introduced.

Throughput semantics explicitly changed: actual builds process sources sequentially,
retaining within-source request.parallelism. The existing multi-source interleaving
helper regression was not relaxed and still passes; it does not establish that
production still interleaves source work. Many short sources can underutilize the
worker ceiling. The smallest follow-up to restore that throughput is a bounded
global queue of native-reader window pages with bounded active source metadata,
using the same scheduler/owners. Loading whole documents in concurrent source
threads would weaken the demonstrated source-lifetime bound and is not this fix.

Remaining gaps: a giant single source still uses full JSON/text/windows; scalar
address metadata still grows with scope. All passages/evidence/semantic results,
classification/report context and topology remain retained. Cached embedding
floats are unchanged. No RSS/physical-read/IPC-cancel or zero-write increment
acceptance is claimed. The two initial red contracts becoming green proves only
the whole-project loaded-document/window-list retention cut.

An expanded run including structural_fact_evidence and semantic_artifact_long_context
had 80 passed / 3 failed in 14.23s. Failures directly exercised unchanged helper
paths: page-wide structural context expectation, one-evidence-per-mention
expectation and one-report-attempt expectation. No before-change baseline was
captured, so these are recorded as unresolved, not asserted pre-existing or passed.

Focused affected-owner validation after source-lifetime/progress changes:

```text
.venv/bin/python -m pytest -q tests/test_native_build_body_budget.py tests/test_native_build_pipeline.py tests/test_native_producer_publication.py tests/test_native_extraction_handoff.py tests/test_native_scalar_grounding.py tests/test_semantic_artifact_scheduling.py tests/test_semantic_artifact_native_extraction.py tests/test_native_embedding_builder.py tests/test_organization_report_product.py tests/test_native_build_worker.py tests/test_native_build_lifecycle.py
88 passed in 25.44s
```

This includes real model-build publication/reuse through no-network fixture
transport, native crash/restart handoff, failure ordering, worker/lifecycle,
scalar grounding, window concurrency, receipts and report-product regressions.
`git diff --check` emitted no whitespace errors. No paid calls or publication.

### 2026-11-04 expanded-regression isolation and contract alignment

The three expanded failures above were isolated without resetting the dirty
checkout: an in-process pytest probe replaced both changed production entrypoints
(`_build_semantic_artifacts`, `_publish_native_topics`) with functions that raise
`AssertionError("source-lifetime changed entry reached")`. All three tests still
failed at their original assertions, and neither probe fired (3 failed in 0.60s).
This excludes those entrypoints from these failures; it is not a clean historical
baseline or a claim about unrelated dirty work.

Two assertions were stale against the current native contract:

- Long extraction now attaches a bounded exact-source identity-context span as
  well as the mention span. The test requires every Ada mention to have exactly
  those two evidence identities, one exact Ada span at a unique absolute position,
  a containing same-representation context of at most name length + 480, and
  context text matching the entity. Existing complete embedding coverage, window
  bounds, receipts, long-tail entity and exact-slice assertions remain intact.
- Native report generation explicitly admits three attempts. The test now
  requires all three attempts to use exactly the same admitted `{e1: Supported}`
  validation context, no canonical storage identity in the prompt, and final
  typed `MODEL_OUTPUT_SCHEMA_INVALID` with `citation_unknown_evidence`. An
  out-of-batch citation cannot be admitted by any attempt. No retry policy changed.

The structural failure exposed an independent shared-helper defect:
`_docling_locations` discarded the known page of a single-page table when a cell
had no bbox. It now retains that unique page while leaving the cell bbox absent;
it never borrows the whole-table box. Multiple table provenances still do not
establish a cell page. The existing red page/table-context test now checks exact
native scalar slices instead of the obsolete no-cell-offset expectation, and
still checks whole-table closure across pages, exclusion of unrelated tables and
explicit-reference closure. A new test requires ambiguous multipage cells to
retain exact scalar addresses with no guessed page or bbox.

Before the helper fix, the aligned four-test selection produced 2 failed /
2 passed in 0.82s: the page-context regression stayed red, the new ambiguous-page
test and long-tail test passed; the report test exposed its intentionally opaque
outer error message, so the final test checks its typed code and safe validator
diagnostic instead of matching private validator text. Only the shared
`_docling_locations` helper and its grounding-context docstring changed production
in this follow-up. No total-plan, dependency, persistence or publication changes.

Final combined validation: the prior 88-test focused selection plus
`tests/test_structural_fact_evidence.py` and
`tests/test_semantic_artifact_long_context.py` passed **107 tests in 25.29s**.
This closes the three recorded expanded failures and adds the ambiguous-page
regression. The source-lifetime and remaining giant-source/global-data limits
recorded above are unchanged. Transport was fixture-only; no paid/network calls.

### Adopted vector bodies in the production result

The source-local `_assemble_source_results` previously retained each complete
float list in `source_builds` after `SQLiteVecStore` had durably adopted it.
Production publication only needs vector IDs, exact source bindings/ranges and
the native owner path. `SQLiteVecStore._read_embedding` still verifies every
bounded vector byte string, finiteness and operation digest but can omit rebuilding
float lists; its default retains the prior direct-call behavior. `_embed_windows`
uses that metadata-only route, and newly accepted vectors are released after the
native adoption. Results retain address/binding identities, never vector bodies.

Red/green: `tests/test_native_embedding_residency.py` observed the 8192-float
vector alive through the assembled publication result before the fix. It now
requires collection after result assembly and still verifies dimension mismatch
rejection. Crash/restart paid-operation tests continue checking durable adoption
and no repayment. Combined reader, vector, source extraction and lifecycle
selection: **83 passed / 27.18s**. This bounds retained in-memory vector bodies,
not accepted SQLite row scans or all per-source evidence/results. No database
schema or stored vector bytes changed.

Final merged owner verification after all G4 cuts in this turn:

```text
.venv/bin/python -m pytest -q [22 focused builder, reader, vector, source, report and lifecycle files]
158 passed in 39.79s
```

Both checkout `git diff --check` commands passed. This is focused source-tree
evidence only; no wheel/bundle build, immutable release artifact, real ESG build,
paid provider, production data or publication was exercised.

### Vector adoption metadata-only repeat path

Red/green: `test_repeated_adoption_without_vectors_does_not_return_float_arrays`
failed before the fix because the already-adopted branch called
`_read_embedding` with its default `include_vectors=True`, even when the caller
requested false. The branch now forwards the requested projection. Both first
adoption and repeated adoption omit `vectors` and preserve operation IDs and the
accepted digest. `_read_embedding` still reads all bounded stored bytes and
validates dimensions, finite float32 values, operation digest and receipt digest
before returning metadata. This is one existing owner/API and no compatibility
path was added.

The new regression also mutates stored rows to prove metadata-only reads reject
both a valid-float operation-digest mismatch and a non-finite float32 even when
the operation digest is updated to match the bytes. The red test failed on the
second adoption before the one-line owner fix. Focused vector, range publication,
embedding builder, extraction handoff, scalar grounding and native extraction
validation passed: **80 passed in 26.41s**; the two added owner-level checks
passed separately (2 passed in 0.09s). No provider call or publication occurred.

### 2026-11-05 raw semantic projection lifecycle

Inspected native ownership at fork base
`24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus ongoing dirty G4 changes:
`_build_semantic_artifacts.source_projection` transfers the source entities,
assertions and relations to the existing reduction stages with `pop`, and
`entity_resolution` releases `entities_by_id` after obtaining the mention list.
Native `_resolve_native_entities` creates canonical KnowledgeEntity values;
`ConflictDetector.reconcile_qualified_facts` delegates grouping to EntityMerger
then creates canonical assertion/relation values. The source dictionaries and
entity lookup must not retain the replaced raw DTOs after those owners finish.
No new storage, model, identity or reconciliation owner was introduced.

Added `tests/test_native_projection_lifecycle.py` against the actual complete model
build using the existing offline transport fixture. It records only weak
references to `_build_source` raw entities/assertions/relations, verifies entities
are collected before fact remapping, and all raw semantic DTOs are collected
before organization. It then completes a ready native publication and compares
canonical scene nodes, visible links and the accepted native project graph with
an uninstrumented build of the same fixture. The generation changes while the
fixture call ledger stays byte-identical. This is fixture replay acceptance,
not a real-provider, real-ESG or release result.

Because the parent implementation was already present when this regression was
assigned, red checks ran in isolated Python processes using an in-memory copy of
`_build_semantic_artifacts`; shared production files were not reverted. Removing
`entities_by_id = None` failed at the post-resolution weak-reference assertion
(`raw source entities still retained`). Restoring assertions/relations indexing
instead of `pop` failed at the post-reconciliation assertion (`raw source
assertions still retained`). The current owner passes. No additional production
change was needed for this seam.

Focused verification:

```text
.venv/bin/python -m pytest -q tests/test_native_projection_lifecycle.py tests/test_native_producer_publication.py tests/test_native_build_body_budget.py tests/test_native_global_body_budget.py tests/test_native_support_copy_residency.py tests/test_project_fact_identity.py tests/test_project_identity.py tests/test_native_semantic_field_fidelity_audit.py tests/test_native_reduction_boundaries.py
62 passed in 32.68s
```

This proves release of replaced object generations, not global bounded memory:
the canonical collections, resolution inputs, source metadata, evidence references
and native fact grouping still need their own scope/resource qualification. Full
fork tests, real ESG build and immutable release/pin validation were not run.
Upstream merge disposition remains pending; rerun this lifecycle and complete
publication fidelity regression after any reduction-owner merge.
