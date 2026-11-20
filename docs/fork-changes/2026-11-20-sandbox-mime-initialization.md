# Initialize document MIME types without host configuration

- Record ID: 2026-11-20-sandbox-mime-initialization
- Date / author: 2026-11-20 / OntoScience engineering
- Status: implemented; focused and installed-wheel verification passed
- Fork base revision: 00e59011ebe95a76d954303d738981808f83c77d
- Upstream reference: not inspected; reproduced with the pinned native runtime.

## Reason and scope

The supplied App log fails during Docling import with EPERM opening
`/etc/apache2/mime.types`. Reproduced with the packaged Python: DocumentConverter
imports the Excel backend, which imports openpyxl; its eager MimeTypes constructor
reads Python's host knownfiles. Semantica records that OSError as DOCLING_IMPORT_ERROR
and fails subsequent parsing. This is independent of the input PDF contents.

## Native capability assessment

- Owner: `semantica/parse/docling_parser.py` import initialization, shared by
  DocumentParser and the semantic worker through source.parse_source.
- Inspected: semantic_worker, semantic_source_artifact, source, DocumentParser,
  FileIngestor's explicit mimetypes.init(), native bundle entrypoint and existing
  cold-process tests in tests/test_semantic_worker_imports.py.
- Repair the existing initialization; retain Docling and Python's builtin MIME
  registry. No new parser, fallback, host permission or dependency is introduced.

## Approach and actual changes

Before importing Docling, remove host MIME configuration inputs and initialize
the standard library registry. Later explicit init calls also remain independent
of host files. Retain built-in MIME support and library-registered additions.
No protocol, stored-data format or processing identity changes; existing parsed
results remain valid. No model calls or network access are needed for the fix.

## Verification and limitations

- Red: the fresh-process denied-MIME regression failed before the owner fix.
- Green: 70 tests passed across `test_semantic_worker_release.py`,
  `test_semantic_worker_imports.py`, `test_pdf_reader_ownership.py` and
  `ingest/test_file_ingestor.py`.
- Built and installed a new wheel in an isolated Python 3.12 environment using
  the existing packaged dependencies and offline models. With an audit hook
  denying host MIME reads, the installed semantic worker parsed a real text PDF
  through Docling and produced a ready reader index and passed quality result.
  This run used the installed wheel, not a source-checkout runtime import.
- Wheel SHA256:
  `794f0152f01913077daac9efee91bb032d9d897b91a06562ea7ab179f1a068dd`.
- Local evidence: sibling `OntoScience-od-dev-runtime/acceptance/` directory,
  `sandbox-mime-20261120/receipt.json`, `verify_installed.py`, PDF and parsed
  artifact. No user profile or daemon data was mutated.
- Release acceptance now denies host MIME reads before loading Docling, so
  future native artifact acceptance exercises this sandbox constraint.
- Acceptance Case delta: keep `journey-library` (primary user outcome) and
  `journey-packaged-mac-startup` (packaged supporting context); no pass criteria,
  baseline or hard gate changed. The fork regressions and installed-wheel run
  are supporting evidence, not full App acceptance.
- Host `change-verification` was not run: this fix changes only the external
  fork, which host changed-path selection does not inspect. Existing unrelated
  host modifications were preserved. Native focused tests above are the direct
  verification of the changed owner.
- No published native artifact, host pin, or installed App was updated in this
  change. Full native-bundle release acceptance and real signed MAS App execution
  on the reporting machine remain separate checks; the installed-wheel run
  simulates the reported filesystem denial rather than a complete MAS sandbox.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Likely overlap: Docling import initialization or Python runtime configuration.
- Drop this adjustment if the canonical runtime provides equivalent host-free
  MIME initialization. Rerun cold-process and document parser ownership checks.
