# Replace the native PDF reader with PyMuPDF

- Record ID: 2026-10-19-pymupdf-native-parser
- Date / author: 2026-10-19 / Codex, requested by repository owner
- Status: implemented; native source regressions passed, installed consumer validation pending
- Fork base revision: d1834228
- Upstream reference: not refreshed for this change
- Related record: [page lifecycle](2026-10-19-pdf-page-lifecycle.md)

## Reason and scope

Same 210-page, 30,850,747-byte original, SHA256
`62e5b2ef1c0ad7eee4a526b81b146c9a48b48e922efb7e177a400239a44ff718`:
pdfplumber took 96.333/82.191 seconds; PyMuPDF took 4.288/4.124 seconds
through the native method registry. The owner requested switching the reader.

## Native capability assessment

PDFParser in semantica/parse/pdf_parser.py owns text, tables, image geometry,
metadata and page numbering. DocumentParser, parse.methods.parse_pdf and ESG's
capabilities worker delegate to it. semantic_artifact_builder has a direct
pdfplumber page-count read. Existing scanned-page, lifecycle, comprehensive parse
and extras tests were inspected. Repair/replace this owner; no new registry,
adapter, alternate backend or silent fallback is introduced.

## Approach and actual changes

Replace pdfplumber calls inside PDFParser with PyMuPDF. Keep output dataclasses,
zero-based input selection and one-based output numbering. Use coordinate-sorted
text, native find_tables and image occurrence rectangles. Close documents on all
paths and do not retain native page objects. Route page-count reads through the
same owner. Replace parse-pdf/semantic-worker dependency and consumer cache
identity. Original bytes and historical caches/evidence remain untouched.
No OCR, model or network calls are added. PyMuPDF licensing is AGPL/commercial;
the fork's MIT declaration does not change the dependency's license.

## Verification and limitations

Native parser/extras regressions: 48 passed, plus 20 subtests. Artifact contracts,
native extraction, grounded source and long-context regressions: 102 passed.
Real generated PDFs cover text/page selection, metadata without page extraction,
tables, image geometry, corruption and encryption. Mocked failure verifies the
document closes on extraction error; scanned-page warnings remain covered.
Invalid negative/out-of-range/noninteger page indices now fail explicitly rather
than silently selecting/skipping pages. `pages=None` helpers now select all pages.

Installed wheel/consumer qualification will be appended after it runs. Reading
order/whitespace can change; the benchmark found text differences on page 210.
Speed does not establish semantic equivalence or ESG delivery quality. No business
production start is implied. The existing structured Docling source path is not
replaced; no email extraction or OCR capability is added.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Overlap: PDFParser, parser dependency extras, metadata consumer and tests.
- Reuse upstream if it acquires an equivalent native owner; do not restore two
  backends as compatibility fallbacks. Recheck output, errors, scanned warnings,
  page selection, tables/images, cache invalidation and native consumer tests.
