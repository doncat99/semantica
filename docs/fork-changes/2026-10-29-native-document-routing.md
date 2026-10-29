# Native document routing

- Record ID: 2026-10-29-native-document-routing
- Date / author: 2026-10-29 / repository contributor
- Status: implemented; focused verification passed, full conversion gate blocked by dependencies
- Fork base revision: a65b15ad1
- Upstream reference: local upstream/main 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0, not refreshed
- Related record: OntoScience native consolidation TODO 2

## Native assessment

`parse/document_parser.py::DocumentParser.parse_document` is the existing native
format dispatcher. `source.py::parse_source` duplicates it for product builds,
including text, PDF, local/remote conversion, EPUB and binary Office. Native
PDFParser and DoclingParser must remain the sole reader/converter owners.
No EPUB parser exists under parse/; its existing spine/safety implementation
can move into that native format module, without claiming the move deletes an
algorithm. Office and remote conversion already have adapters; reuse them.

Callers: semantic_source_artifact -> parse_source; native parse/parse_batch,
parse.methods and ingestion use DocumentParser. Existing source, Office,
remote-Docling, Docling lease, PDF ownership and cold-worker import tests apply.
The eager parse package and eager parser construction must become lazy so a
text-only worker does not load document models or require optional formats.

## Intended change

Make parse_source a contract/quality adapter delegating once to parse_document.
Native dispatcher admits MIME/OCR and selects the explicit processing profile;
no error fallback or double conversion. Preserve default native parse API and
product document shape, text offsets, provenance, processing/content identity.

## Verification / limits

New red specs prove delegation for text, PDF, EPUB and Office. Case
capability-library-prepare / primary journey-library, delta keep. No acceptance
criteria, hard gates or baselines change. No paid calls or runtime data mutation.
Product acceptance and immutable release remain unverified.

2026-10-29 implementation: source delegates once; admission and explicit profiles
belong to DocumentParser. EPUB moved to parse/epub_parser without rewriting the
spine algorithm. Public exports and format instances load lazily. Native PDF
resolves its canonical reader at use, preserving coordinates/content sort options.
No pdfplumber or preliminary reader was added. Office tests now create the files
they claim to parse, because native admission checks file existence.

Evidence: 44 focused source/Office/EPUB/ownership/cold-import tests passed;
final same selection plus Docling lease lifecycle: 50 passed.
native PDF coordinates/content profiles passed 2/2 in the complete base env.
Broad conversion run: 73 passed, 14 failed, 1 skipped before the PDF factory fix;
two factory failures were corrected and verified separately. Remaining 12 use
an installed upstream Docling lacking recover_formula_regions. A source-overlay
attempt yielded 60 passed/13 failed: incomplete fork dependency installation left
PdfPipelineOptions unavailable. These runs are not full conversion acceptance.
Remote tests also expose an existing immutable-checkpoint/task-state conflict;
both direct failures reproduced with HEAD owners loaded unchanged. Track under
TODO 6; no claim of remote lifecycle health or real ESG acceptance.

Task-only runtime delta: +298/-559, net -261 lines. This includes moving 97 EPUB
lines and deleting eager optional-export scaffolding/docstrings; it is not a
claim that all removed lines were duplicate algorithms. source.py routing itself
is +13/-238. Upstream delta remains fork-wide and includes concurrent work;
the inspected upstream reference above is unchanged and not a fresh merge audit.

## Upstream assessment

Extend native dispatcher; do not restore independent source routing on merges.
Re-run source/profile, EPUB safety, Office, PDF and cold-import gates.
