# Bounded native document structure closure

- Record ID: 2026-11-04-native-document-structure-closure
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe; dirty main
- Upstream reference: not inspected
- Related issue / PR / commits / records: G4 reader owner cut; pending

## Reason and scope

The native document reader served scalar chunks and exact ranges, but could not
return bounded structural dependencies for tables or native nodes. The separate
builder still loads a full parsed JSON artifact; changing that path is explicitly
out of scope and is not claimed bounded by this record.

## Native capability assessment

- Existing owner: `semantica.semantic_document_reader.write_reader_artifact` and
  `read_document_reader`; canonical native scalar traversal is in
  `semantica.parse.document_reader.project_document_reader`.
- Callers/tests checked: `DocumentReaderRequest`, worker reader route, native
  reader tests and G4 capability probe `tests/test_native_document_range_audit.py`.
- Decision: extend the current reader and its SQLite address index. The G4
  `_closure` process remains a capability probe, not production implementation.
- No duplicate document carrier or body mirror is introduced.

## Approach and actual changes

- `structure` selection accepts explicit text/picture/group refs or table cell
  refs and bounded roots, bytes, objects, depth and SQL work.
- Canonical publication records byte addresses/digests for native node fields
  and cells plus an R-tree of table row/column header spans. SQLite stores no
  body text. Reader index format advances to v3; old indexes require rebuild.
- Reader follows caption, footnote, rich-cell and parent refs while returning
  original typed fields; table selection includes only span-related row and
  column headers. Oversized cell text must use scalar ranges.
- Changed files: `semantica/semantic_document_reader.py`,
  `semantica/semantic_query_schema.py`,
  `tests/test_native_document_reader.py`,
  `tests/test_native_document_reader_structure.py`.
- No model/network/dependency/runtime data changes. No builder or
  `semantic_source_artifact.py` changes. The whole-source JSON load remains.

## Verification and limitations

- Regression red before implementation: `tests/test_native_document_reader_structure.py`
  rejected `field=structure` and roots in the production `DocumentReaderRequest`.
- Focused tests: `.venv/bin/python -m pytest -q
  tests/test_native_document_reader_structure.py
  tests/test_native_document_reader.py tests/test_native_document_range_audit.py`:
  27 passed in 13.71s. `git diff --check` passed for all changed paths.
- Not run: builder bounded-memory acceptance, model/network/production data, installed
  bundle, full suite.
- Risks: header span and closure rules need more adversarial coverage (multi-page
  ambiguous provenance, deep shared dependency graphs, very large dependency lists).
  The API transports only bounded requested closure; callers remain responsible
  for using it instead of parsing canonical JSON directly.

## Upstream merge assessment

- Disposition: pending; incoming revision not reviewed.
- Likely overlap: native document reader and parser projection.
- Adaptation: preserve one reader owner and remove v2 index assumptions; do not
  add compatibility reads for old index artifacts.
- Required checks: document reader, schema/worker routes, installed artifact and
  future builder consumer validation.

## Dated follow-ups

- 2026-11-04: red production request/schema regression preceded implementation.
  The added native reader tests select a bounded body cell plus merged column
  header, row header, caption, footnote and rich child among 1500 unrelated
  nodes and a huge unselected cell; assert original native values/refs, no
  sibling closure, address-only storage and bounded bytes/objects. Budget and
  missing-address failures are explicit. Existing publication cycle rejection
  remains covered by `test_native_document_range_audit.py`.
  Builder whole-artifact loading remains an open G4 gap. No installed bundle or
  builder consumer validation was run.
- 2026-11-04: follow-up regression reproduced a false cycle for a caption whose
  parent points to its table while the table references it as a caption. Reader
  metadata now queues caption/footnote node traversal until the active node is
  complete. A separate forged-address fixture creates an actual self-child
  cycle with a matching per-object digest; closure rejects it. Structural plus
  native reader tests: 23 passed in 1.49s. `git diff --check` passed.
