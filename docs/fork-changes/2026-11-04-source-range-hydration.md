# Exact demand-driven source range hydration

- Record ID: 2026-11-04-source-range-hydration
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected
- Related records: native source-window work in current dirty checkout

## Reason and scope

The artifact builder needs arbitrary evidence quotations after dropping source
bodies. Existing extraction windows have fixed boundaries; loading parsed JSON
to hydrate a selected quotation defeats demand-driven reads.

## Native capability assessment

- Owner inspected: `semantic_document_reader.py::_read_source_windows`, its
  source-map and scalar-segment indexes, and `read_document_reader` validation.
- Callers/tests inspected: `semantic_artifact_builder.py` window consumers,
  `semantic_source_artifact.py::_load_parsed_source`,
  `tests/test_native_source_windows.py`, `tests/test_native_document_reader.py`.
- Decision: extend the existing source-window reader to accept one arbitrary
  bounded range. No new content storage, parser, cache, or alternative reader.

## Approach and actual changes

- `read_source_text_range(request, start=..., end=...)` reuses installation,
  header, scalar proof and source-map validation. Returns one exact Unicode
  range, its native addresses, and physical bytes read.
- Range maximum: 12,288 code points; existing physical byte, fanout,
  cancellation and execution bounds remain enforced. Oversized or invalid
  requests fail explicitly. No stored-data/worker protocol change or migration.
- Source-map lookups now seek the predecessor of the requested start and use
  both lower/upper index bounds instead of visiting the earlier source prefix.
- No model/network calls or new dependencies. Builder integration is owned by
  the coordinating change; this record alone does not claim G4 completion.

## Verification and limitations

- Before implementation, the four format cases failed with missing-helper
  ImportError, establishing the red specification.
- `.venv/bin/python -m pytest -q tests/test_native_source_windows.py
  tests/test_native_document_reader.py tests/test_document_reader_index.py`:
  39 passed. Arbitrary offsets match the existing whole-document oracle across
  Docling, PDF text, EPUB and flat ODF, including Unicode and native range
  descriptors. Physical-byte bounds, cancellation, invalid/oversized/out-of-range
  requests and changed-installation rejection are covered. Query plans assert
  both index bounds and absence of a source-map scan.
- No release, packaging, real ESG execution, or formal-data changes performed.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Likely overlap: native source-window reader. Retain only while upstream lacks
  equivalent arbitrary range support; adapt to the canonical owner if added.
- Re-run native source-window and reader tests after merge.
