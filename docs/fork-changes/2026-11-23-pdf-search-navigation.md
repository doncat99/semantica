# Preserve native PDF search navigation provenance

- Record ID: 2026-11-23-pdf-search-navigation
- Date / author: 2026-11-23 / OntoScience maintainers
- Status: verified-in-stated-scope
- Fork base revision: 79ea845d08c506615d070af223521e9123343207
- Upstream reference: not inspected for this focused repair
- Related: OntoScience Explore search-navigation regression

## Reason and scope

A keyword hit had an exact native scalar range but no PDF page. The canonical reader resolved page 10, while `_document_hit` replaced that locator with the coarse index-row locator. The host consequently opened page 1 and could not focus the keyword. Result-buffer counts also cannot identify a PDF occurrence after continuation.

## Native capability assessment

Existing owners inspected: `semantic_query.py::_document_hit`, `semantic_document_reader.py::read_document_reader`, `parse/document_reader.py::project_document_reader`, `explorer/search_index.py::GraphSearchIndex.search_native_positions`, query/reader schemas and tests, at the base revision above. Repair these owners. No parser, search index or document representation is duplicated.

## Approach and actual changes

- Keep the reader-resolved locator; remove index-row override.
- Resolve one unambiguous native PDF provenance region with existing indexed scalar addresses. Return normalized top-left geometry and a region-local keyword occurrence ordinal, independent of query-wide/buffer offsets.
- Read only the bounded scalar prefix needed to count preceding occurrences. Existing 64 KiB scalar, physical-byte, metadata and cancellation limits still apply. Adjacent segments of the same provenance region share an ordinal. PDF-text uses its canonical page as the region.
- `QueryHit.pdfFocus` is the current optional focus contract; query-wide `matchIndex` retains its existing meaning. OntoScience must forward and consume the new focus contract. Existing immutable reader artifacts already contain the required provenance; no migration, source reparse, reindex or paid model call is required.
- Ambiguous/unlocated provenance does not invent geometry. Oversized ranges retain explicit native budget failure.

## Verification and limitations

Red regression failed on the old owner with `hit.locator.page is None` for an actual DoclingDocument with page-10 provenance and page-less index locator. The repaired test covers query offsets 0/128/256 and a provenance region spanning the 16 KiB scalar boundary.

`.venv/bin/pytest -q tests/test_native_query.py tests/test_native_document_reader.py tests/test_pdf_reader_ownership.py`: **51 passed**. No network/model calls in the new test. Native artifact qualification and packaged host acceptance are separate subsequent gates; focused tests do not claim them.

## Upstream merge assessment

Disposition: keep pending incoming-upstream review. No incoming upstream revision reviewed. Overlap: native range reader, query assembly and QueryHit schema. Retain one canonical implementation; after merge rerun native query/reader/ownership tests and consumer PDF navigation acceptance. Replace this fix if upstream owns equivalent correct behavior.
