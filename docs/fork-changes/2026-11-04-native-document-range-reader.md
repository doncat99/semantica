# Native document range reader and address-only publication

- Record ID: 2026-11-04-native-document-range-reader
- Date / author: 2026-11-04 / Codex reader implementation agent
- Status: verified-in-stated-scope
- Fork base revision: `24ef31681` (working tree already contains reconstruction work)
- Upstream reference: installed Docling Core native document/cell/provenance definitions; upstream Git ref not refreshed
- Related records: `2026-11-04-native-document-range-capability-audit.md`, `2026-11-03-native-persistence-g1-audit.md`

## Reason and scope

The prior reader projected native document content into stored reader text and
page text, introducing another full content carrier. Rebinding a source could
also regenerate those carriers. G1 established that native Docling refs, text
scalars, cell coordinates and provenance suffice for a range reader, while
native export-to-text is a full serialization and cannot serve a bounded read.

This change implements the G2 reader seam only. Parser normalization, source
receipt authorization, installed identities and host contracts are coordinated
changes owned by the reconstruction parent; focused reader checks do not prove
those integrations or packaged product acceptance.

## Native capability assessment

- Native content owner: Docling `DoclingDocument`, native body child order,
  `TextItem.text`, `TableCell`, `RichTableCell.ref`, `ProvenanceItem` and native
  `BoundingBox.to_top_left_origin`. Plain text/PyMuPDF remain their existing
  native scalar owners.
- Existing callers inspected: `semantic_source_artifact.py`, document reader
  worker request schema and prior reader projection/index tests.
- Decision: replace mirrored reader persistence in the existing
  `parse/document_reader.py` and `semantic_document_reader.py` owners with
  addresses into the unique canonical native JSON. No replacement parser,
  table serializer, knowledge graph, content identity or query ranker is added.

## Approach and actual changes

- Parsed source protocol is exclusively `semantica.parsed-source.v3`; the index
  is exclusively `semantica.document-reader-index.v2`. Old carriers and embedded
  `document.reader` are rejected. Docling wrapper text/plain_text/doctags mirrors
  are rejected. There is no compatibility read branch.
- Publication streams JSON in 16 Ki codepoint scalar fragments. SQLite records
  native scalar byte addresses/digests and locator descriptors, never body text.
  Descriptor insertion is incremental and SQLite cache is limited to 2 MiB.
- Native table cells retain coordinates/header flags. Rich cells read their
  referenced native child once, not their formatted text mirror; blank cells
  retain their coordinates. Missing cell boxes remain coarse; table boxes are
  never substituted for individual cell locations.
- Page addressing uses actual native charspans and bounding boxes. Bad native
  provenance remains an explicit invalid layout; no guessed text location is
  introduced. Offsets are local to `nativeRef` in `native-scalar` coordinates.
  Cross-page Unicode scalars retain one content scalar and exact per-page
  charspans. Page native/OCR/mixed states use the converter's cell-origin
  metadata; missing origin remains `document_text`, never guessed per scalar.
- `metadata.header` contains protocol/materialRevision/representationRevision/
  format and available mimeType/forceOcr/processingRevision/documentProcessing/
  contentHash. Quality is only `{version,status,issueCount}`; issue quote bodies
  are not copied into the index. Header UTF-8 must fit 4096 bytes or publication
  fails explicitly. `metadata.readerHeader` stores the small returned format,
  indexFormat, chunkCount, pagePartCount and pageCount object for direct rebinding,
  with exact textCharCount, pageStateCounts, processingProfile and ready/partial
  status derived during the same incremental publication. No status consumer
  needs to load native document content to derive these aggregates.
  Existing metadata format/artifactDigest/chunks/pages remain; there are six
  explicit keys. Source ID belongs to the authorized request, not canonical
  shared content.
- Reads seek at most 128 indexed descriptors, read at most five native scalar
  segments per range, validate actual segment digests and enforce a physical
  source-byte budget of `min(selection.maxBytes, 256 KiB)`. Transport output has
  its own maxBytes check. An indivisible item exceeding either budget produces
  `DocumentReaderBudgetError`, never silently shortened text.
- Cancellation, 30-second query deadline, descriptor size (16 KiB), native ref
  depth (64), visited item count (1,000,000), page count (100,000), and installed
  file identity before/after reads are enforced. Cursor progression is checked.
- Page selection uses the indexed `pageNumber` and page-local `pagePart` seek;
  per-page counts avoid reading other pages. Chunk selections reject a page
  number. Whole-document cursors remain global descriptor ordinals.
- No dependency, model, network or official profile operation is introduced.
  Obsolete derived outputs require the parent-owned explicit reset/rebuild;
  readers do not migrate old formats during normal reads.

## Verification and limitations

Command:

```
.venv/bin/python -m pytest -q -s tests/test_native_document_reader.py tests/test_document_reader_projection.py tests/test_document_reader_index.py
```

Result: **16 passed in 1.22s**. Includes Unicode/escape-heavy complete paging,
native table/cell coordinates, invalid provenance, subprocess restart, unchanged
canonical payload, index without body, source rebinding, bounded metadata,
cancellation, explicit old protocol rejection and transport/physical limits.

For 160,000 versus 8,000,000-character native text publication, Python traced
peak allocation was **272,484 vs 286,328 bytes** (input allocated before tracing).
This is Python allocation evidence, not a total RSS or native SQLite memory
measurement. G0 fixtures report native body 13,312 bytes with **0 duplicated
reader body bytes** and source body 16,896 bytes with **0 rebound output/content
bytes**.

Not verified here: full host integration, source/parser gate alignment, all
supported input formats, real ESG data, package release, App navigation or model
token records. EPUB/flat-ODF require an explicit single native representation in
the parser seam; they are not handled through fallback text readers. PDF-text
exposes exact native page text ranges with actual page counts and explicit
`invalid_layout` when nonblank text has no coordinates. Dimensions or boxes are
never fabricated; these pages are not validated page-layout navigation.

## Upstream merge assessment

- Disposition: pending incoming upstream review. This is a necessary range
  access extension around the existing native content owner, not evidence that
  upstream lacks all range facilities permanently.
- Recheck Docling native refs, rich-cell semantics, provenance and serializer
  capabilities on upgrade. If the owner gains a bounded native range interface,
  delegate and delete the superseded custom address implementation together.
- Required checks: the G1 native capability probe, G2 production reader tests,
  source rebind tests and all parent-owned host/worker acceptance gates.

## 2026-11-04 follow-up: exact-range location preservation

Exact native ranges now retain the indexed structural/page locator rather than
returning only scalar offsets. The existing address index adds an expression
index on field/ref/start; lookup is constrained to the same 16 Ki scalar segment,
at most 128 candidates per field/range and 256 KiB cumulative descriptors. Page
selection uses actual native page charspans; multiple matching pages do not
fabricate a page. Missing location index requires explicit representation rebuild.
No body projection, PDF parser, dependency or fallback was added.

Verified: `tests/test_native_document_reader.py`,
`tests/test_native_document_range_audit.py`, `tests/test_native_record_worker.py`
**41 passed (19.46s)**; `/tmp/semantica-g4-evidence-location-final.log`.
Coverage includes PDF page 7, Unicode offsets, cross-page Docling ranges, missing
index rejection and SQLite EXPLAIN indexed lookup without table SCAN. Host exact
evidence reader/routes tests separately passed 17/17 and tests typecheck passed.
Immutable artifact rebuild, relocated acceptance and App navigation remain pending;
the index-format identifier alone is not qualification of old artifacts.
