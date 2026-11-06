# Native document keyword occurrences and pagination

- Record ID: 2026-11-02-document-keyword-search
- Date / author: 2026-11-02 / project contributor
- Status: verified-in-stated-scope
- Fork base revision: fca3600cd79b90513671ca7a0752b4002e1857b6
- Upstream reference: local `main` inspected; no upstream commit supplying this protocol
- Related records: `page-knowledge-graph` acceptance case

## Reason and scope

Knowledge Research keyword search was returning one aggregate knowledge hit per
document and the host then capped the result set, so a literal such as `ESG`
lost occurrences, page locations and in-file previous/next navigation. The
scope is the native query owner: enumerate literal occurrences from already
admitted canonical parsed-source artifacts, with bounded pagination and precise
locators. Semantic knowledge search and graph storage are out of scope.

## Native capability assessment

- Existing owner and inspected files/symbols: `explorer/search_index.py` and
  `semantic_query.py`; callers are the worker query protocol and the host
  Knowledge Research route.
- Decision: repair/extend the native query owner. The host only supplies
  authorized artifact paths/digests and forwards pages.
- No second index, graph, snapshot, embedding store or copied source is added;
  each page reads the existing parsed-source-v2 artifact and validates its
  digest and representation identity.

## Approach and actual changes

- `GraphSearchIndex.document_matches`: escaped, case-insensitive literal
  occurrence enumeration with total and next offset.
- `semantic_query_schema.py` / `semantic_query.py`: explicit `documents`
  target, authorized document references, precise `DocumentLocator`,
  page-local `matchIndex`, and bounded pagination.
- Tests cover 1,205 occurrences, page two, Unicode offsets, source identity and
  rejection of snapshot loading for document search.
- No model, network, dependency or persistent-data cost is introduced.

## Verification and limitations

- `.venv/bin/python -m pytest tests/test_document_keyword_search.py
  tests/test_semantic_query_worker.py`: 29 passed.
- Host route/query tests: 116 passed; web graph protocol tests: 24 passed.
- Full host typecheck remains blocked by pre-existing graph-dashboard errors
  (`LayerClusterNode`, `KnowledgeUnderstandingScene.layers`), outside this
  change.
- Pages are bounded at 1,000 results by protocol; callers must follow
  `nextOffset` for larger totals.

## Upstream merge assessment

- Disposition: pending upstream review. Keep only while upstream lacks a native
  document-occurrence query contract; remove this extension if that capability
  lands upstream with equivalent locators and pagination.
- Required after merge: rerun worker tests, host route/query tests and the
  `page-knowledge-graph` primary E2E.

## Dated follow-ups

- 2026-11-03 cancellation correction: the host previously stopped waiting but
  drained the active query, blocking the next serial request. The existing
  `semantic_query_worker.serve` now reads bounded cancellation frames while one
  query executes. A request-local cancellation event reaches the existing
  keyword reader, canonical hydration and `SQLiteVecStore.search_groups`;
  SQLite progress handlers interrupt active SQL. Terminal responses preserve
  the worker and installed indexes. No parallel query pool or alternate search
  implementation is introduced. Host termination remains the bounded recovery
  for an unresponsive worker. Regression coverage exercises active JSONL
  cancellation, actual SQLite interruption, scratch cleanup and subsequent
  requests. Packaged cancellation latency and full acceptance remain pending.

- 2026-11-03: inspected `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
  plus the search working changes. `query_semantic_artifact` remains the sole
  worker query owner. Document queries never use `ContextRetriever`; defer its
  import until the knowledge branch so a fresh document worker does not load
  knowledge/vector retrieval dependencies. A fresh isolated-process regression
  failed before the change. No query, ranking, authorization or integrity
  semantics change; packaged cold-latency qualification remains required.
  Renewed worker/document/location/persistent-vector regression selection:
  160 passed (`python -B -m pytest`, 2026-11-03). A fresh native development
  artifact is being built; this is not immutable release qualification.
- 2026-11-02: added native document occurrence pagination and graph-selection
  presentation changes; no host-side search index or duplicate knowledge layer.
