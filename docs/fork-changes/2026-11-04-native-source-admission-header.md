# Native source admission header and structure projection ownership

- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Inspected revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus existing dirty remediation work
- Upstream assessment: pending; no incoming upstream revision inspected

## Native owner and scope

Inspected `semantic_document_reader.write_reader_artifact`,
`_read_document_reader`, the source-map/window indexes,
`semantic_source_artifact._load_parsed_source`, and builder
`_docling_locations` / `_window_grounding_context` callers. Existing native
indexes support body-free binding metadata but lacked document MIME identity and
source-window extent counts required for build admission. The builder's exact
structure projector exists and must be reused rather than approximated by the
different interactive structure-reader closure.

## Actual changes

- Current reader header now includes document MIME identity, source character
  count, and window count. It contains no new body projection.
- `read_source_header(request)` delegates to the current installed native
  reader's binding, metadata-size, cancellation, and before/after installation
  checks. It opens the canonical source but reads zero source bytes.
- The existing `_bbox` / `_docling_locations` projection was moved unchanged
  from the builder to `parse.document_reader`; the builder consumer imports the
  same implementation. This preserves exact location semantics, including
  native provenance, rich cells, section paths, formula/code original text,
  notes and traversal order. It is still a production-time whole-document
  projection, not a claim that build-time structure is now bounded.
- Coordinated builder scheduling/admission consumption is recorded separately
  by the source-streaming change. No compatibility reader, protocol dispatch,
  duplicate content store, new dependency, or published artifact was added.

## Verification

`tests/test_native_source_header.py` checks complete admission metadata while
guarding canonical body reads, plus material binding, cancellation and changed
installation rejection.

`.venv/bin/python -m pytest -q tests/test_native_source_header.py
tests/test_native_source_windows.py tests/test_native_document_reader_structure.py`:
16 passed, no model or network calls.

Existing index/native reader and semantic grounding/extraction regressions:
`.venv/bin/python -m pytest -q tests/test_document_reader_index.py
tests/test_native_document_reader.py tests/test_semantic_artifact_grounding_budget.py
tests/test_semantic_artifact_native_extraction.py`: 61 passed.
Touched production files pass `git diff --check`.

## Limits and merge assessment

This does not close G4: full source bodies, structural context hydration and
global candidates require the remaining builder work. Header metadata must be
produced by the current writer; unsupported old data needs explicit rebuild,
not a fallback. Packaged artifact qualification, real ESG execution, full
repository checks, release pins and formal user data were not touched.

Upstream disposition remains pending. Reuse an equivalent upstream native
owner if introduced; rerun current reader and builder structure oracles after
merge rather than retaining a parallel projection.
