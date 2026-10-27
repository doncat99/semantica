# Reject the local pdfplumber backend rollback

- Date: 2026-10-27
- Base: d44dd1583a57df34854a3b2300e81f8c4cde37d4
- Reason: an uncommitted old text-flow draft replaced the already migrated
  PyMuPDF owner, removed metadata/render/link APIs and weakened page validation.
- Native owner: semantica/parse/pdf_parser.py::PDFParser. Inspected parse,
  extract_metadata, render_pages, _parse_page, callers in the native parser
  registry and artifact builder, and existing parser lifecycle/scanned tests.
- Approach: restore the committed PyMuPDF parser, usage documentation and scanned
  tests. Retain sort=True and explicit sort=False overrides. Historical
  pdfplumber use_text_flow=False is not a request to invert PyMuPDF's sort.
- Prevention: extend the existing reader-ownership gate to forbid pdfplumber
  even inside PDFParser; document the backend requirement in AGENTS.md. No
  second parser, fallback, dependency or runtime option is added.
- Regression: the strengthened ownership suite failed on the local rollback:
  1 failed, 18 passed, identifying pdf_parser.py's pdfplumber import.
- Dependency cleanup: remove the obsolete pdfplumber CI pin, its sole
  pdfminer-six dependency and stale provenance comments. Other dependency pins
  are unchanged; this is not a full lock-file regeneration. Update the extras
  test to follow the existing semantic-worker-common dependency rather than
  require PyMuPDF to be repeated in each platform extra. Assert every worker
  extra includes PyMuPDF, with no pdfplumber declaration or CI install pin.
- Verification: 119 passed and 20 subtests passed across reader ownership,
  dependency extras, PDF lifecycle/scanned/construction/comprehensive parsing,
  artifact contract and kernel owner suites (7.68 seconds). Five existing
  PyMuPDF/SWIG deprecation warnings. The first expanded run had 117 passes and
  one stale worker-extra assertion failure, corrected as described above.
  The ownership scan covers every tracked production Python file, including
  examples and sparse paths; no production pdfplumber import remains.
  git diff --check passed. No package publication, production-data write or paid
  model call is part of this repair. Unrelated drafts are retained.
- Upstream assessment: no incoming merge. The existing committed native owner
  already supplies the required implementation; remove the obsolete local
  replacement instead of adding compatibility code.
