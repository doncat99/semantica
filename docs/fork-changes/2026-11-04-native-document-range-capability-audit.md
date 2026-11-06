# G1: unique native Docling JSON and address-only range capability probe

## Reason and inspected native owners

G1 needs evidence before deleting the redundant reader projection. This change
is a test-only capability investigation, not an implemented reader replacement.
Inspected Semantica HEAD `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` and its
installed/locked PyPI `docling-core==2.103.1`. Canonical Docling checkout HEAD
is `9baa3e0eeea6b77bb957687b71840b7ff84a390e`; its own lock/venv uses core
2.102.0. No docling-core source checkout was found under external-sources.

Native `DoclingDocument.load_from_json` reads the complete JSON string.
`extract_items_range` operates on an already loaded model. `RefItem.resolve`
indexes the native document's in-memory lists. `DocSerializer.serialize(item=)`
exists, but caption, footnote and excluded-ref caches traverse its document.
`MarkdownTableSerializer.serialize` uses the whole grid, headers, column types
and tabulate. These APIs do not establish bounded on-disk serialization.
The inspected lock has no streaming JSON tokenizer dependency; optional orjson
does not supply this capability and is not installed in the inspected venv.

## Test-only implementation and affected files

`tests/test_native_document_range_audit.py` publishes one native-schema JSON
while a synthetic parser-owned native model exists. It uses standard-library
JSON encoding, direct recursive traversal of native `model_fields` and
address-only SQLite tables:
`addresses(ref, offset, length, digest)` and
`scalar_segments(ref, codepoint_start, codepoint_end, offset, length, digest)`.
Both use `WITHOUT ROWID`; SHA256 digests are 32-byte blobs. Normal items have
item/text addresses, not rows for each ordinary metadata field. Containers
have required metadata addresses, table cells have an object address, and only
oversized cells additionally have individual field addresses. Root identity
and individual native pages are addressable. No native schema content field is
copied into SQLite.
It does not implement text/table formatting,
store plaintext in the index, invoke PDF readers/models/network, or modify any
production producer or consumer. Native JSON model validation round-trips the
same document content and provenance. The probe does not claim byte identity
with native `save_as_json`, which performs its own full-document allocation.

An independent Python process uses indexed seek/read and digest verification
to recover the selected native text field or native TableCell. It covers emoji,
CJK, combining marks, escaped quote/backslash/newline, OCR item parent and page
provenance, repeated cell values and identical cell bboxes. A table with two
physical-page provenance entries remains explicitly coarse: native TableCell
does not supply a page identity, so no cell page is guessed.

## Verification

` .venv/bin/python -m pytest -q -s tests/test_native_document_range_audit.py `
returned **6 passed in 38.52s**. Actual fixture measurements:

| Quantity | Bytes |
| --- | ---: |
| Unique native document JSON | 1,632,982 |
| Address-only SQLite index | 249,856 |
| Deep text field read | 21 |
| Returned text JSON allocation measurement | 21 |
| OCR native TextItem read | 297 |
| Native TableCell read | 297 |

These counters measure selected source bytes and encoded returned value size,
not total Python RSS, module import I/O, SQLite page I/O, or production latency.
The index includes both native TextItem and text-field addresses for this
capability probe; it is not an approved production index-size budget.

### Oversized native scalar continuation

The test-only publication writer encodes string slices of at most 16,384 Python
codepoints with the standard JSON encoder. It emits their escaped interiors
between one pair of quotes, preserving one native JSON scalar and its exact
decoded Unicode sequence, including combining marks. It never encodes another
full string copy. Native text fields longer than 16,384 codepoints get sparse
segment addresses and digests; no segment contains text in SQLite. Existing
native `orig`/`text` fields remain native schema fields, not newly added mirrors.

A fresh subprocess finds only the overlapping segment range using the
`(ref, codepoint_start)` primary key. Tail lookup uses descending primary-key
order with `LIMIT 1`, not a full segment aggregate. Each raw segment is bounded
before read, hashed, wrapped in quotes and decoded with standard `json.loads`.
No tokenizer, table formatter, DocTags or secondary plaintext representation is
added. Actual SQL range plans contain primary-key SEARCH and no SCAN/temp sort.
Native document-model roundtrip passes for both sizes.

| Measurement | Small scalar fixture | Large scalar fixture |
| --- | ---: | ---: |
| Native JSON bytes | 168,620 | 8,400,620 |
| Address SQLite bytes | 12,288 | 24,576 |
| Same 30-codepoint source range read bytes | 62,558 | 62,558 |
| Encoded returned value bytes | 91 | 91 |
| Additional traced publication peak bytes | 219,609 | 231,297 |
| Fresh-process traced range-read peak bytes | 292,451 | 292,451 |

Tests also cover empty ranges, exact segment boundaries and the final segment.
The source grows about 50-fold without growing the selected read or range-read
allocation. Allocation tracing begins after parser-owned model construction and
after reader imports. It excludes baseline model memory, Python RSS, SQLite C
allocations/page I/O and kernel buffering. Thus this is evidence of bounded
additional Python scalar encoding/decoding, not a full-process memory or total
storage-I/O budget. The many-item fixture's address index is now **15.3%** of
the native source, reduced from the earlier 112% metadata-per-field probe.
The sparse segments deliberately trade bounded read amplification for fewer
index rows: a 30-codepoint selection crossing two segments reads 62,558 bytes,
not 4KiB. Its explicit source-read budget is **256KiB**; two 16Ki-codepoint
segments require at most 196,608 escaped bytes for valid Unicode. This is a
measured capability parameter, not an implicit claim of a production budget.

### Large table publication without another object tree

Publication recursively visits native fields and never calls `model_dump`.
An additional test monkeypatches `BaseModel.model_dump` to raise throughout
publication, then validates the resulting complete native JSON after restoring
the native method. The native parser-owned input exists before allocation
tracing starts. No table grid, list of copied cells, full encoded table or
replacement document is constructed.

| Measurement | 20 rows / 40 cells | 2,000 rows / 4,000 cells |
| --- | ---: | ---: |
| Native JSON bytes | 12,297 | 1,172,303 |
| Address SQLite bytes | 12,288 | 352,256 |
| Additional traced publication peak bytes | 14,959 | 29,890 |

The table source grows about 95-fold while additional traced Python publication
allocation grows by 14,931 bytes. Reading its last selected cell stays below
1KiB after a fresh-process restart. The larger table's address index is 30.0%
of source; the small fixture illustrates fixed SQLite page overhead. Neither
figure is a general storage budget, and tracing still excludes SQLite native
allocation and parser-owned native model memory.

### Existing consumers and the actual table requirement

Inspected the current host consumer contracts, not only parser output:

- `apps/daemon/src/knowledgehub/file-detail.ts::loadSemanticaFileContent`
  returns bounded `chunk.text` strings joined by separators. It exposes text,
  continuation and source identity, not a whole-table byte-equality contract.
- `apps/daemon/src/knowledgehub/semantica/document-layout.ts::projectSemanticaDocumentLayout`
  requires page dimensions and text blocks with physical geometry. It neither
  interprets Markdown table alignment nor requires its global column widths.
- `apps/daemon/src/knowledgehub/course-studio/course-phase-artifacts.ts::previewCoursePhase`
  returns a page's native items; `correctedCoursePhasePreview` addresses a table
  cell by native item reference and cell index.
- `apps/web/src/ontoscience/course-studio/course-page-layout.ts::coursePageLayout`
  reads native `table_cells`, their text and bbox to draw editable overlays.
  It does not parse Markdown. Its current use of the owning table's page for
  cells still must not imply proven per-cell precision on multi-page tables.
- `semantica/parse/document_reader.py::project_document_reader` currently
  demands exact equality between its complete native serialization and an
  already stored full text mirror. This is an internal projection invariant
  imposed by the implementation being removed; it is not evidence that the
  product requires global table Markdown padding to remain byte-identical.

Therefore use native text/cell identities and physical provenance as the
consumer contract. Do not carry whole-table Markdown offsets forward as native
source offsets. Bounded extraction may serialize a native table fragment for
the model, but that fragment is a transient view, not an independently stored
body or a claim to be the original full-table byte range. Changes to source
locators/DTOs still need coordinated host/fork tests before deleting the old
producer. Existing corrections and precise physical-location expectations
must be retained, or marked explicitly unknown where native provenance lacks
the information; no guessed page assignment.

### Native table/closure experiment: concrete failure and viable seam

The third test uses only native `MarkdownDocSerializer`, `TableData` and cell
models. Its table has a merged two-column header, two body rows, rich-cell
references, caption and footnote. There are 1,500 unrelated text items.

- `serialize(item=table)` visits **6,022** native items to serialize this tiny
  table. Global excluded/caption/footnote bookkeeping defeats bounded access.
- Native `add_node_items([table])` copies one rich child into `#/texts/0` but
  leaves the table's caption at `#/texts/1500`, footnote at `#/texts/1501`,
  and rich-cell reference at `#/texts/1502`. Subsequent native serialization
  raises **IndexError**. This is now a reproduced remapping/closure defect,
  not a hypothetical gap.
- A native fixture containing only header + first row and correctly attached
  native dependencies serializes with **22** native visits. Merged-header
  structure, rich escaped text and caption survive. This hand-assembled fixture
  proves serializer behavior only; it does not implement automatic closure.
- The first data row differs between complete/subset output: `1` is left
  aligned in the full table (a later row makes that column textual), and right
  aligned in the subset (the selected column is numeric). Widths differ too.
  Byte-equivalent global Markdown ranges require information from omitted rows;
  returning the subset's formatting must not claim such equivalence.
- Native `serialize_footnotes(item=table)` returns the correct footnote, but
  native table serialization itself omits that footnote. Consumers requiring
  the footnote must request it as a typed dependency, not assume it was emitted.

### Bounded structured dependency closure

The final two tests use the same native JSON and address-only index.
A fresh process loads selected native cells and TextItems, plus only their
required caption, footnote, rich-cell, child and parent-metadata dependencies.
Native `TableCell`, `RichTableCell` and `TextItem` models validate selected
objects; native field annotations validate container metadata. It preserves
original refs instead of constructing a second DoclingDocument or remapping
sparse refs into artificial local lists. Parent traversal never loads parent
children or siblings. No native whole-table grid or Markdown serializer runs.

The fixture contains 1,500 unrelated preceding items, a 1,000-row table, a
merged header, a row-spanning rich cell, an unselected oversized cell,
caption/footnote/rich refs at high original IDs, and OCR text with a picture
parent and physical provenance. Selecting two cells and the OCR item reads
**1,766 bytes across 20 addressed objects** from **2,941,293 source bytes**.
Only the selected dependencies and table/picture metadata appear in output.
Original row/column spans, source refs, parent refs and provenance survive.

Cumulative bytes, objects, depth and a two-second request deadline are bounded.
Missing refs, child dependency cycles, identity/digest mismatch and limits are
explicit states in the test helper. Tests exercise missing refs, dependency
cycles and object/byte/depth rejection. Selected oversized cell text can be
read by the same bounded scalar range seam, while the cell's native coordinate
field is independently read in one byte; a full oversized cell closure still
returns an explicit byte-limit error. It does not silently omit text.

### Current implementation route and owner boundary

The demonstrated route for the inspected consumers is **one native Docling
JSON + necessary address metadata in Semantica, with bounded native structured
views at request time**. No evidence requires a new table formatter, a new
docling-core fork or a core serialization API before these consumers can work.
The earlier recommendation making core formatter changes a prerequisite was
too broad and is withdrawn. Do not implement it as part of this remediation.

G2 must replace the duplicate reader producer and every UI/CLI/HTTP consumer
together. Typed page contracts must carry selected native text/cells,
captions/footnotes/rich dependencies, original refs, physical provenance,
location precision and continuation. Preserve item-ref/cell-index correction
keys. A multi-page cell without native per-cell page identity remains explicitly
coarse, never assigned a guessed page. Large text and cells must remain fully
reachable through continuation under enforced budgets. Do not retain the old
reader mirror as a fallback, persist these views, or format a table only to
parse it back into structured data.

The native full/subset Markdown and `add_node_items` defects remain separate
upstream audit evidence. Investigate core changes only if an actual consumer
later demonstrates a need for bounded native formatted fragments; the current
structured consumers do not establish that requirement.

## Explicit gaps and consumer boundary

- Bounded scalar continuation and direct native table-field publication are
  proved in this synthetic test seam. Production reading/publication remains
  unchanged. Isolated UTF-16 surrogates are not accepted by this UTF-8 emission
  recipe. Image/binary fields and arbitrary native custom field serializers
  are not covered by these fixtures. Production adoption must define accepted
  native input fields and explicit text validity, index-size, object and process
  budgets; it must not assume an arbitrary Pydantic model is serializable by
  this test helper.
- TableCell structural access is viable without whole-table serialization.
  It is not proof that formatted whole-table Markdown can be reproduced for an
  arbitrary range without reading other cells. No formatter was added.
- A production reader may expose native text/codepoint ranges and native
  table/cell structure. That consumer boundary must be explicit; no silent
  downgrade from promised whole-table formatting or precise physical location.
- Structured dependency closure is proved only in the test helper, not a
  production protocol. G2 must implement the coordinated typed metadata-plus-
  scalar continuation contract, source/index admission and cancellation.
  Total RSS/SQLite I/O and production index-size budgets remain unproved.
  Sparse original list IDs must never be satisfied by allocating preceding
  items. Native subtree Markdown serialization is not a current prerequisite.
- Existing Semantica reader tests still return **6 passed, 1 failed**; the
  interleaved table/emoji reader projection failure remains real. This native
  range capability investigation passes its six tests; it does not certify
  all G1 owners or imply G2 production implementation or release acceptance.
  G2 protocol/admission implementation is a following gate, not an additional
  prerequisite invented for this G1 capability experiment.

## Upstream merge assessment

Pending. Recheck native serializer/ref/JSON capabilities on dependency upgrades.
Prefer a demonstrated existing native interface over retaining a test probe as
a production subsystem. This change introduces no new dependency or fork.
