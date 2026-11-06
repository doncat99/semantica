# Native source-window reader

- Record ID: 2026-11-04-native-source-window-reader
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe; dirty main
- Upstream reference: not inspected
- Related issue / PR / commits / records: G4 native reader builder-consumption prerequisite; pending

## Reason and scope

The semantic builder's `_text_windows` consumes a flattened native source
projection with exact codepoint offsets and format-specific separators. Existing
reader pages were fixed scalar segments and could not substitute for those
windows without changing extraction text or native grounding coordinates.
This adds a paged native-reader query prerequisite only; the builder remains
unchanged and still loads parsed source JSON in full.

## Native capability assessment

- Existing owner: `semantica.parse.document_reader.native_scalar_projection`,
  canonical publication/read owners in `semantica.semantic_document_reader`,
  and builder oracle `_text_windows`.
- Callers/tests checked: parsed-source artifact writer, `DocumentReaderSelection`,
  native reader, scalar grounding and structural window tests.
- Decision: extend current reader index with address/boundary maps and query;
  no content store, second document representation, or compatibility reader.
- Exact oracle is the existing builder's `_native_text`, `_native_grounding_ranges`,
  `_window_native_ranges` and `_text_windows` over transient canonical payloads.

## Approach and actual changes

- Add ordered source-window and native-scalar address maps to the current
  SQLite reader index. Only offsets, native refs, separator markers, and window
  extents persist; body text remains only in canonical JSON.
- Add paged `field=source_windows` reader results with bounded window count,
  mapping count, transport bytes, physical bytes and cancellation checks.
- Preserve text/PDF/EPUB/flat-ODF separators and Docling native scalar order.
  Window offsets use the established structural/sliding chunkers; an exact
  arithmetic fast path avoids copying unambiguous long single-scalar input.
- Changed files: `semantica/parse/document_reader.py`,
  `semantica/semantic_document_reader.py`, `semantica/semantic_query_schema.py`,
  `tests/test_native_document_reader.py`, `tests/test_native_source_windows.py`.
- No builder, source-artifact, model, network, dependency, artifact, pin or
  release changes.

## Verification and limitations

- Red spec: cross-format tests initially failed because `source_windows` was
  absent from the production selection contract.
- Red: `tests/test_native_source_windows.py` failed before schema/reader support
  because production `DocumentReaderSelection` rejected `source_windows`.
- Focused command: `.venv/bin/python -m pytest -q
  tests/test_native_source_windows.py tests/test_native_document_reader_structure.py
  tests/test_native_document_reader.py tests/test_native_document_range_audit.py`:
  35 passed in 15.03s. This includes the existing 8 MB scalar publication
  allocation gate and structure/cycle regressions. `git diff --check` passed.
- Cross-format source windows equal the old builder text, exact structural
  windows, and clipped native-range oracle for Docling, PDF text, EPUB and
  flat ODF. Fixtures include empty elements, Unicode combining/supplementary
  characters, headings, lists, code and >280 KB source bodies. Body-free SQLite
  map check and indexed range query plan pass. Per-window native stream reads
  are <=32 KiB (two 16 KiB segments), each page stays within its 256 KiB cap,
  and pre-set cancellation yields typed cancellation failure.
- `tests/test_native_document_reader.py` confirms publication allocation for
  8 MB single-scalar text remains within the established 512 KiB delta budget.
- Binding quality metadata preserves only the sorted three-code admission
  whitelist (`formula_transcription_missing`, `fragmented_cjk_encoding`,
  `unmapped_characters`) plus version/status/count. A 40KB issue quote is not
  copied into reader metadata. Source-window adversarial tests reject more
  than 258 map rows for one selected window and reject a forged missing extent;
  neither truncates to partial success.
- The exact writer currently computes transient flattened text and lets the
  existing structural chunker return its chunk descriptors at publication.
  The unambiguous long single-scalar fast path is bounded, but this is not a
  proof that publication-side temporary allocation is bounded for every large
  structured document.
- Builder integration and whole-source JSON load removal are not implemented.

## Upstream merge assessment

- Disposition: pending; incoming revision not reviewed.
- Likely overlap: native reader index and parser source projection.
- Preserve one canonical reader/index; old index formats require rebuild.
- Required future checks: exact builder windows/ranges, builder semantics,
  source-level memory, all consumer contract checks, installed artifact.

## Dated follow-ups

- 2026-11-04: red/green selection support, exact four-format window/range oracle,
  cancellation and read-bound evidence recorded above. No builder edits or
  builder-consumer success claimed.
