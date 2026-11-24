# PDF search address and reading-order repair

- Record ID: 2026-11-25-pdf-search-focus-addresses
- Date / author: 2026-11-25 / OntoScience maintainers
- Status: verified-in-stated-scope
- Fork base revision: 1ad5a0bbed927660440ee80597de2abf31e4076a
- Upstream reference: not inspected; targeted fork repair
- Related records: 2026-11-23-pdf-search-navigation; 2026-11-24-keyword-index-recipe-identity

## Reason and native capability assessment

The OntoScience ESG Report audit found saved Docling provenance with valid pages
and boxes but spans extending past trimmed text by two separator characters.
`parse/document_reader.py::project_document_reader` rejected the complete address.
Its caller `semantic_document_reader.py::write_reader_artifact` already owns the
address projection; repair it in place, intersecting valid spans with native text.
`explorer/search_index.py::GraphSearchIndex` owns occurrence ordering and all
forward/reverse cursor paths. Block bounding boxes cannot order multiple matches
inside one block; mixed columns also require native reading order. Order by
source, page, native scalar, ordinal and relative offset. No token coordinates
are fabricated, and column transitions may legitimately move upward.

## Approach, callers and stored data

The current native lexical recipe changes, requiring explicit startup rebuild by
the host. `native_maintenance.py::rebuild_reader_index` delegates to the canonical
writer on one saved representation (64MiB bounded input, host subprocess deadline).
It verifies installation, artifact digest and material/representation identity,
requires distinct staging paths, and verifies the regenerated content digest is
unchanged. It never opens the original PDF, calls a parser/model or replaces the
installed original. The host installs the derived index by content digest before
adopting receipts, then uses existing `rebuild_keyword_index`. Interrupted work is
retryable without paid operations. Existing native publication/generation/vector
identities are retained. No alternate query/read path is introduced.

## Verification and limitations

74 tests passed: test_document_reader_projection.py, test_native_keyword_owner.py,
test_docling_search_locations.py, test_native_document_reader.py,
test_document_reader_index.py and test_pdf_reader_ownership.py.
Red evidence preceded the projection, ordering and maintenance implementation.
Regressions cover clipped provenance, forward/reverse continuation across 128
results, saved-byte preservation, repeated maintenance and invalid installation.
Host real-data acceptance and packaged release qualification remain pending.
No full upstream suite or OCR recall claim.

## Upstream merge assessment

Disposition: keep this native-owner repair pending upstream review. No upstream
revision reviewed. Conflicts likely in the projection, cursor sort tuple and
maintenance CLI; retain the same span validation, reversible reading order,
immutable saved bytes and no-model migration guarantees after merges.
