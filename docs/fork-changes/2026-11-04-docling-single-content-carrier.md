# Native Docling single content carrier (G2)

The normal OntoScience conversion path now requests native Docling JSON only.
`DocumentParser` and the remote Docling client no longer request or return
parallel DocTags. `DoclingParser(include_document=True)` does not implicitly
export DocTags; an explicit library `export_format='doctags'` remains available.

For Docling conversion, the sole persisted content carrier is native Docling JSON. Native
`DoclingDocument.export_to_text()` supplies transient quality/extraction input,
including native table serialization, instead of the deleted handwritten JSON
text walker. Accompanying page descriptors contain page numbers, dimensions and
page-level origin from actual converter `TextCell.from_ocr` evidence,
not copied page bodies, tables or images. Normal conversion disables the separate
table extraction output. Plain text and Markdown sources use the same current
`format='text'` contract.

Remote responses must contain valid native JSON and must not return unrequested
text/DocTags content. Native JSON validation precedes result adoption. The
remote parser and normal source parser no longer read/write document or remote
response checkpoints. Remote task identity belongs to the existing host job:
`remoteTask={}` grants one submission after durable host submission intent;
`remoteTask={taskId}` polls that existing task without reading/uploading source
bytes. A submission progress event returns only task identity. Unknown submission
outcomes require explicit reconciliation, never automatic submission retry.
The canonical source header exposes the actual parser, version and origin so
the host does not duplicate parser routing rules for native text/Office inputs.
This does not claim removal of the remaining G3 checkpoint implementation or
production data cleanup.

Remote transport enforces 64 MiB source, 90 MiB encoded request, 128 MiB native
result and 64 KiB task/status response budgets. Reads stop at the budget plus
one byte and reject excess explicitly; content is never silently truncated.
Task identity is limited to 1024 UTF-8 bytes. Submission keeps bounded transient
upload encodings but writes no remote response or content cache. Resume does
not read or encode the source again.

Current follow-up verification: **101 passed** across parser, remote, source,
quality, reader, reader projection/index and the parser-no-checkpoint guard.
This includes the real `parse_source` worker entry without any checkpoint,
process kill followed by a fresh worker resuming the host-supplied task ID with
exactly one total submission, typed JSONL refusal of unknown submission state,
and remote-profile native text succeeding with no remote submission grant.
Invalid/parallel response content and byte-budget excess are rejected without
persisting response bodies. A cross-page table without per-cell page identity
retains native cell text once and reports `invalid_layout` instead of inventing
page membership. Old offline checkpoint tests that still require normal parser
checkpoint reads are intentionally not satisfied by a fallback; their migration
contract remains part of G7 work.

Current processing identity is derived from the normalized actual processing
profile, MIME, material suffix, OCR option, and the installed native parsing/
reader implementation. It is a SHA-256 output, not a caller-controlled revision
salt. A fixed small set of relevant owner files and format/mode-relevant package
metadata is hashed once per process/recipe; no heavy parser import, environment
enumeration or document read is introduced for this calculation. Bind and load
both reject a changed profile or recipe. The bind index header retains the actual
parser/version/origin. Unchanged rebind stores zero new content bytes and reads
no canonical JSON body into memory. Cold worker import isolation remains tested.
For optional Office conversion, the actual installed `office-release.json`
receipt is also hashed with a 64 KiB read ceiling on every recipe calculation;
changing the installed capability invalidates reuse without scanning its files.

The retired historical parsed-source importer was physically deleted together
with its worker route, schema and compatibility tests. Current reads cannot
upgrade an older carrier implicitly. Downstream offline reset/cleanup remains
a separate gate; this removal does not claim old formal-profile data was deleted.

Exact current native test selection:
`tests/test_document_reader_index.py`, `tests/test_semantic_worker_imports.py`,
`tests/test_project_remote_docling.py`, `tests/test_project_source.py`,
`tests/parse/test_docling_single_content.py`, `tests/test_native_document_reader.py`,
`tests/test_document_reader_projection.py`, `tests/test_project_document_quality.py`,
`tests/test_project_office.py`,
`tests/test_source_native_parser_owner.py`,
and `tests/test_no_checkpoint_runtime.py`.

## Retained format adapters

Office conversion previously stored section bodies, a joined full text, and
the complete flat-ODF XML. The current Office adapter persists only
`sections[].text` with structural locators. EPUB likewise retains only its
native spine sections. No global text offsets, page numbers or geometry are
invented for these formats. The source/build loader joins sections transiently
when computation requires text; the reader indexes addresses into the canonical
section scalars and reads only the requested ranges.

The parser → canonical writer → build source-loader → paginated reader →
zero-content-byte rebind regression covers `.doc`, `.ppt`, `.xls` and `.epub`.
It verifies paragraph ordering, multiple slides, repeated spreadsheet row/cell
extent, EPUB spine/href identity, absence of body mirrors, and no fabricated PDF
pages. The Office external executable boundary alone is substituted because no
LibreOffice capability is installed in this run; real ODF extraction and all
other listed production owners execute. This is not a claim of actual binary
Office conversion acceptance. Fresh-process section range reads additionally
cover EPUB/paragraph/slide/cell locators with Unicode and <=65,536 bytes per
requested part, identical before and after process restart. Initial red specs
produced seven failures (unsupported section reader and repeated Office bodies)
before replacement; the expanded current native selection passes 101 tests.

G2 owns parsing, the single native content carrier, faithful structural reader
locations and source-loader handoff. G3 owns extraction/handoff and G4 owns
knowledge/query consumers. Their use of all source fields remains required:
passing this native selection does not pass downstream graph/search mapping.
The existing search-index consumer's v2-only admission is an explicit later
integration blocker; restoring a v2 carrier or compatibility reader is prohibited.

Owners changed: `parse/document_parser.py`, `parse/docling_parser.py`,
`project_remote_docling.py`. No Docling fork changes or PDF parser replacement.
The host and source-artifact owner separately bind the v3 source-independent
carrier and native reader index; this record does not declare those gates passed.

Verification: parser/remote/PDF ownership/project-source suites: **48 passed**. Native text
contract red specification: both `.txt`/`.md` failed on the replaced format
labels before the fix. Remote JSON-only specification failed on the former
three-format requirement before the fix. Local conversion uses real
`docling_core` document/table models with a stub converter: actual full Docling
converter was not used in that initial focused run. Generic explicit DocTags
export passes. The subsequent offline converter verification below closes the
local native/OCR/mixed converter gap; it does not replace packaged acceptance.

Fresh combined parser/remote/PDF/source/native-reader/index run: **59 passed**.
An explicit source-only integration harness also exercised host
`readDocumentReader` → `SemanticaWorkerSession` → production JSONL
`semantic_query_worker` with a real `docling_core` document containing Unicode
text and a native table cell. Installed canonical content and body-free reader
index were reused across two fresh worker processes; chunk pagination and a
page-specific read returned identical content after restart. Physical reads
were respectively 14, 12 and 26 bytes in both processes. Evidence is recorded
in the host's ignored `.tmp/g2-native-reader-process-evidence.json`.
The harness uses an explicit developer `PYTHONPATH`, not a packaged runtime;
this proves the process contract only. Exact immutable artifact installation,
and real App acceptance remain separate unpassed gates.

## Offline real converter follow-up

Reused the existing host bundle `7301ab4dbd6323132fa8296491abbb9988df360504125a64c227bf59a769f5e9`
runtime (`docling-slim 2.141.0+ontoscience.2`, `docling-core 2.103.1`) and its
installed models. No dependency/model installation or paid model call occurred.
The source-only harness sets Hugging Face offline flags and rejects every IPv4/
IPv6 socket connection, so success cannot depend on a hidden network download.

The real three-page PDF contains native text, image-only text, and a page with
both. With OCR enabled, converter cells supply origins `native/ocr/mixed`; the
installed reader reports `native_text/ocr_text/mixed_text` and reads 19/16/37
canonical bytes. With OCR disabled it reports
`native_text/no_text_content/native_text` and reads 19/0/21 bytes. Each page was
also read in a fresh Python process with identical results. Native cell origins
are persisted only as small page metadata; no cell text copy or fabricated
per-scalar OCR attribution is introduced. Unknown origin remains honest
`document_text`.

Red specifications demonstrated missing page origins and incorrect generic page
state before the fix. A real native Unicode scalar with three page provenance
charspans now returns one chunk and the exact page-specific slices, retaining
its nativeRef. Parser/native-reader/projection/index focused run: **24 passed**.

Reproduction harness: host `.tmp/g2-converter-evidence.py`; evidence saved to
host `.tmp/g2-converter-evidence.json` (original converter scratch path:
`/var/folders/tk/3tsfn0ps4y7_9q55g26q24700000gn/T/ontoscience-g2-converter-jyilklai/evidence.json`).
This explicitly selects the current source with `PYTHONPATH`; immutable release
installation and real App/ESG acceptance are still unpassed downstream gates.

Expanded current run: **65 passed** across
`tests/parse/test_docling_single_content.py`, `tests/test_project_remote_docling.py`,
`tests/test_project_source.py`, `tests/test_project_document_quality.py`,
`tests/test_native_document_reader.py`, `tests/test_document_reader_projection.py`,
and `tests/test_document_reader_index.py`. The host-to-JSONL-worker process
harness was rerun after page-origin changes, retaining fresh-process range
equivalence and the same bounded byte reads. This closes these stated native
parser/reader checks only; the parent G2 gate still requires worker identity
admission and course parity/golden classification before it can pass.
