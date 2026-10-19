# PDF reader ownership review and regression gate

- Record ID: 2026-10-19-pdf-reader-ownership-review
- Date / author: 2026-10-19 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 470aa5e2308d4327354fc32e3bbd2186d1725c12
- Upstream reference: not inspected; review concerns this fork's tracked tree
- Related records: [reader switch](2026-10-19-pymupdf-native-parser.md)

## Reason and scope

User requires a whole-repository review prohibiting direct PDF reader calls that
bypass PDFParser, and an explicit account of Semantica versus Docling backends.
The checkout is sparse: inventory uses the complete Git tree, including absent
examples, integrations and notebooks, rather than only materialized files.

## Native capability assessment

- Basic text, pages, images, tables and metadata: `parse/pdf_parser.py::PDFParser`.
  The only production PyMuPDF import/open is inside that owner.
- `DocumentParser`, `parse_pdf`, and snapshot progress metadata delegate to it.
- Structured documents/OCR: existing `parse/docling_parser.py::DoclingParser`
  delegates one conversion to Docling. `source.py` and method dispatch reuse it;
  remote profiles use the existing Docling service contract.
- Docling's reader is a dependency implementation, not a direct reader opened by
  an application caller. Retain its native structured conversion; do not add a
  preliminary PyMuPDF parse or force DoclingDocument creation through plain text.
- Email PDF extraction is an unsupported placeholder returning None, not an
  active reader bypass. Its old pdfplumber wording is misleading.
- Tests may use a reader to generate fixtures or verify the native backend.
- Decision: reuse existing owners; enforce boundaries, no alternate parser.

## Approach and actual changes

- `AGENTS.md`: enforce reader ownership, including metadata, subprocess tools and
  structured Docling conversion. Reader use in fixture generation stays permitted.
- `tests/test_pdf_reader_ownership.py`: AST-based check of every tracked production
  Python file, reading index contents when absent in a sparse checkout. Rejects
  direct imports, literal dynamic imports and literal reader command invocations;
  negative controls exercise these bypasses. Uses only stdlib plus pytest.
- `.github/workflows/ci.yml`: execute this gate before optional extras installation.
- `tests/parse/test_docling_parser.py`: verify the default native Docling backend;
  existing one-conversion test now also blocks PyMuPDF/fitz imports.
- `ingest/email_ingestor.py`: correct obsolete guidance and debug wording; PDF
  attachment extraction remains unsupported (None). No new extraction behavior.
- No parser algorithm, dependency, cache identity, stored evidence, model call,
  network request, budget, worker count or project control state changed. Runtime
  package remains the previously qualified wheel; this governance change does
  not require stopping/redeploying the parser. No new reader wrapper was added.

## Verification and limitations

Complete tracked-tree review: 1,012 Python files (488 outside tests), 40 notebooks,
plus shell/config references, at the stated base revision. `git grep HEAD` inspected
sparse-excluded files too. No remaining active direct reader bypass was found.
The previous snapshot-builder pdfplumber bypass is already gone at this base.
Notebook/shell reader references were searched manually; they are not parsed by
the Python AST gate. Tests/fixtures are exempt from production import restrictions.

Inspected call graph:

| Caller | Native owner | Actual reader/conversion |
| --- | --- | --- |
| `DocumentParser` PDF branch / default `parse_pdf` / extraction helpers | `PDFParser` | PyMuPDF |
| snapshot progress page count | `PDFParser.extract_metadata` | PyMuPDF, no page extraction |
| `parse_pdf(method="docling")` / `parse_document_docling` | `DoclingParser` | Docling converter |
| local structured `source.parse_source` | `DoclingParser` | Docling converter, one conversion |
| remote structured source | `project_remote_docling` | existing service protocol, no local reader |
| PDF ingestion / provenance | file ingest | raw bytes, no semantic PDF interpretation |
| email PDF extraction | unsupported placeholder | no reader, returns None |

Live installed runtime inspection: Docling 2.139.0 with
`docling-slim 2.139.0+ontoscience.2`, default
`docling.backend.docling_parse_backend.ThreadedDoclingParseDocumentBackend`,
`docling-parse 7.22.3`. Explicit full-page OCR selects
`docling.backend.pypdfium2_backend.PyPdfiumDocumentBackend` (`pypdfium2 5.14.0`).
Neither is a PyMuPDF backend. Installed backend sources were inspected as well as
dependency metadata. Changing PDFParser does not change Docling readers, native
rendering, OCR work, or structured conversion performance.

Verification command (fork cwd; ESG's isolated qualification interpreter):

```sh
/Users/huangdon/Documents/ESG_DataCenter/.venv-semantic-pdf-acceptance/bin/python -m pytest -q \
  tests/test_pdf_reader_ownership.py tests/parse/test_pdf_page_lifecycle.py \
  tests/parse/test_pdf_scanned_detection.py tests/parse/test_parse_comprehensive.py \
  tests/parse/test_docling_parser.py tests/parse/test_parser_construction.py \
  tests/test_project_source.py tests/test_pyproject_extras.py \
  tests/test_project_remote_docling.py tests/test_native_grounded_source.py \
  tests/test_semantic_artifact.py
```

Result: **110 passed, 20 subtests passed**, 6 dependency deprecation warnings,
14.91 seconds. Evidence: ESG
`data/audits/pdf-reader-ownership-20261019/native-tests.log`.
CI-interpreter check: `uv run --no-project --python 3.11 --with pytest python -m
pytest -q tests/test_pdf_reader_ownership.py`: **14 passed**, 2.29 seconds;
`ownership-py311.log` in the same evidence directory. The initial system Python
3.11 had no pytest; this isolated uv environment did not modify runtime packages.
Initial gate development exposed non-shell strings and BOM source encoding;
the gate now checks command call sites and lets Python decode source bytes.
An attempted notebook AST pass encountered an existing markdown-as-code cell;
notebooks remain manually reviewed rather than silently skipping syntax errors.

Limitations: static enforcement cannot prove arbitrary dynamically constructed
imports, aliased loaders, indirect shell commands or future reader dependencies
safe. Review remains necessary. Docling conversion tests use an injected converter;
no new real OCR/structured-PDF performance test or paid model run occurred. Remote
service internals were not reviewed. This is PDF ownership review, not whole-repo
functional certification or end-to-end ESG acceptance. CI workflow was edited;
remote CI outcome is separate from the local checks above.

## Upstream merge assessment

- Disposition: keep ownership rules; adapt if upstream relocates native owners.
- Incoming upstream revision: not yet reviewed.
- Likely conflicts: parser modules, CI and contributor rules.
- Retain one basic reader owner and one structured conversion owner; never use an
  allowlist entry to admit business parsing outside them. Re-run ownership and
  parser/source tests after any upstream merge.

## Dated follow-ups

2026-10-19 / Codex: completed the stated review and local gate/consumer checks.
Kept existing native capabilities; no competing reader implementation or redundant
PDF preparse was introduced. Production acquisition was not resumed.
