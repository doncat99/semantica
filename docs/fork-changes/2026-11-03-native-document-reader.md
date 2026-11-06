# Native document reader projection

- Record ID: 2026-11-03-native-document-reader
- Date / author: 2026-11-03 / OntoScience integration
- Status: focused and immutable native artifact verified; product acceptance blocked before run creation
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty native index work preserved)
- Upstream reference: not inspected; no upstream merge claimed
- Related changes: Docling reading-order provenance repair in its canonical fork checkout

## Reason and scope

Host layout concatenated texts before tables while the source reader walked body
references and joined table cells differently. Cross-page dehyphenation in Docling
also generated invalid native provenance; that defect is repaired in Docling,
not compensated in Semantica or TypeScript.

## Native capability assessment

- Inspected DocumentParser._parse_conversion, DoclingParser._extract_pages,
  SourceDocument, semantic_source_artifact and semantic_artifact_builder._docling_locations.
- Reuse DoclingDocument iterator and PlainTextDocSerializer; no PDF reader,
  recognition, semantic algorithm or alternative serialization is introduced.
- SourceDocument publishes the reader alongside the retained native representation.
  The builder's semantic evidence mapping retains its separate responsibility.
- Callers: OntoScience document layout, source-text reader and Course Studio phase preview.

## Approach and actual changes

- parse/document_reader.py projects native serialization into ordered chunks and
  native per-page spans into top-left layout. Invalid positions remain invalid.
- source.py produces the projection before representation hashing.
- Binding an existing parse projects retained native data, preserving source bytes.
- Host consumers delete raw collection/body traversal. Old projections require
  explicit preparation; GET never reparses, calls a model or repairs native spans.
- No protocol version ladder or dependency is added. Native PDF and generic text
  retain their explicit format paths; they do not switch to a different parser.
- No network/model calls. Persisted projection adds bytes to the parse artifact;
  complete artifact download is not claimed to be bounded storage paging.

## Verification and limitations

- Initial reader specification failed because no canonical reader projection existed.
- `uv run --no-sync pytest -q tests/test_document_reader_projection.py tests/test_docling_search_locations.py tests/test_pdf_reader_ownership.py tests/test_project_stages.py tests/test_semantic_artifact.py`: 89 passed.
- Native Docling regression: 3 failing cases before repair, 7 passing after repair.
- Docling `make validate`: clean second run after formatter adjustment.
- Host reader/layout, runtime, research/course projections, preparation and publication: 98 passed; retained-parse projection keeps historical bytes and does not parse again.
- Immutable native artifact `sha256:b2b8bafe3df14cfb4495cacaa42e251591ccb8642d1713ae7c1be4a01eb096fe`: 34,718-file inventory and relocated acceptance passed (486,229 ms); post-run inventory and parser dependency closure verified. Subsequent cache verification passed. This binds the frozen build inputs, not later documentation edits.
- Installed bundle imports under Python `-I -B` passed hard-hyphen, soft-hyphen and Unicode three-page Docling-to-reader assertions. Installed query test passed (18.48 s); two earlier fixture-generation attempts timed out at 120 s, with diagnostic stacks in transformers import. Cold-start performance is not qualified by the later pass.
- Host final change-verification selection (`knowledge-secondary-states,course-studio`) completed preparation but run creation rejected source changes in the shared workspace. No product cases executed in that attempt; no baseline or freeze checks bypassed. Host evidence: `.tmp/docling-boundary-change-verification-current.log` and `.tmp/docling-boundary-delivery-20261103.md`.
- Complete suite and release publication pending; release pins unchanged. No production source processing or paid model requests performed.
- Existing corrupted native coordinates require explicit source repair to regain
  exact locations; projection alone cannot infer the lost truth.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Reuse an equivalent native exporter if upstream adds one and delete this adapter.
- Retest serialized table order, Unicode spans, invalid provenance and host consumers.

## 2026-11-03 bounded reader publication and query update

- Native parse/bind publication now streams the existing representation into its
  immutable JSON while recording chunk/page byte references in a sibling SQLite
  index. The index contains offsets, lengths, digests and a bounded identity
  header; it does not copy document text or introduce another parser.
- `readerHeader.chunksDigest` and `pagesDigest` are hashes of canonical UTF-8 JSON
  arrays, accumulated while writing each item. Consumers compare native reader
  equivalence without loading all chunks/pages.
- The current query worker exposes `reader` for source-scoped chunk/page reads
  before graph adoption. Both artifacts require verified installation identities.
  SQLite seeks only requested ordinals and the reader validates individual byte
  ranges and digests. Continuation preserves every item, including Unicode.
- Limits: 128 entries, 4 MiB source bytes, 2 MiB SQLite cache, 30 second query
  deadline, cancellation checks and explicit failure for an oversized entry.
  The publisher's bounded source header allows the host to verify streamed
  digests without parsing the complete document a second time.
- Native focused validation: reader index/projection, query worker, semantic
  artifact and project stages: 116 passed. Production acceptance and publication
  remain separate gates; the formal host release pin is unchanged.
- Scope limits: native conversion/bind still owns the complete document needed
  for its requested conversion. A single native layout page or generic text
  chunk exceeding 4 MiB is rejected by the reader; producer subdivision is not
  claimed here. Historical carrier migration is an explicit offline operation,
  not an automatic fallback from ordinary reads.
