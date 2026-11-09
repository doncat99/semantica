# Upstream 0.8 source sync and build-performance assessment

- Record ID: 2026-11-09-upstream-sync
- Date / author: 2026-11-09 / fork maintainer tooling
- Status: verified-in-stated-scope
- Fork base revision: `916ec8bc88579a671067a09bec3fc2fc69871f71`
- Upstream reference: `39cf7216d2326b012436efebf8a227e82f37dd3b` (`upstream/main`, fetched 2026-11-09)
- Related records: [native fact/source reuse](2026-11-08-native-fact-source-reuse.md), [snapshot API removal](2026-11-05-knowledge-snapshot-api-removal.md), [PDF owner](2026-10-27-pdf-backend-rollback-repair.md)

## Reason and scope

Review and integrate the 84 incoming upstream commits, and determine whether
upstream addresses the observed native fact reconciliation/sealing bottleneck.
This is a source merge into fork `main`, not a worker artifact release, App
update, consumer pin change, real-data migration or new ESG/model execution.
Existing uncommitted performance work is preserved separately and restored after
the merge; it is not part of this sync commit.

## Native capability assessment

Inspected upstream history, source and tests for graph traversal, context,
provenance, conflict resolution, export, parsing, vector and triplet stores,
configuration and build orchestration. Existing owners are reused in place.

Upstream has no `semantic_publication_builder.py`,
`triplet_store/qualified_fact_index.py` or `triplet_store/publication_records.py`.
There are no incoming changes to `oxigraph_store.py`, `entity_merger.py` or
`conflict_detector.py`. Consequently this sync does not directly fix the fork's
observation-read, canonical decision import or sealing joins. No performance
improvement for that path is claimed.

## Approach and actual changes

Retain upstream graph edge indexing and causal-chain adjacency traversal;
rank-first context retrieval and node embedding fixes; endpoint/confidence export
corrections; strict provenance failure propagation and injective checksum encoding;
Blazegraph/Jena/RDF4J read filters; vector pre-limit filtering and score direction;
DOCX/media/PDF API corrections; TOML standard-library loading; server build and
fresh pipeline-builder fixes; security/dependency and documentation updates.

- Package version becomes 0.8.0. Python support becomes 3.11–3.13 and Pillow
  floor becomes 13.0.0. Regenerate and validate the universal `uv.lock` against
  the merged manifest. Retain exact fork Docling wheel URLs/hashes, PyMuPDF,
  worker optional-dependency ownership and absence of core `grpcio`.
- Preserve `PDFParser`'s PyMuPDF implementation. Adapt five incoming default-page
  tests to PyMuPDF mocks instead of restoring pdfplumber. Keep the upstream API
  docstring correction; default/None/selected/empty-page behavior remains tested.
- Exclude upstream snapshot-grounded RAG commit `cd1c5d40` (#1731): its new
  assembler/provider/index, exports, tests and docs require deliberately removed
  full truth-snapshot contracts. Preserve the current native indexed,
  version-fenced context filter and temporal owner. Do not add a second carrier
  or restore obsolete snapshot storage performance tests.
- Adapt upstream credibility handling `40d40dcc` (#2052): missing credibility
  returns the existing unresolved `ResolutionResult`; it must not silently
  switch to first-seen and claim a resolved value. The replacement regression
  was observed red against the incoming implementation before the source fix.
- Keep upstream graph index changes together with the fork's `itertools.chain`
  bounded iteration. Keep the GC timing harness correction and its three tests.
- Remove incoming trailing whitespace in two tests. No business-result identity,
  paid receipt, fact ID, vector row or stored extraction is rewritten.

## Upstream performance evidence and issue research

- [PR #1932](https://github.com/semantica-agi/semantica/pull/1932),
  `4f348c63`: index ContextGraph edge types once instead of scanning edges for
  each pair in community/centrality algorithms. Author reports 6,000-edge label
  propagation 21.2 → 1.44 s and PageRank 20.6 → 0.09 s. These are upstream
  author measurements, not App measurements. Incoming access-count tests pass.
- [PR #2121](https://github.com/semantica-agi/semantica/pull/2121),
  `b8f37138`: causal-chain BFS builds adjacency once, replacing repeated full
  edge scans. Author reports 8,000-node star 6.3568 → 0.042 s. Again an upstream
  measurement; incoming scaling/access-count tests pass here.
- [Issue #807](https://github.com/semantica-agi/semantica/issues/807), closed:
  provenance SQLite transactions/N+1 lineage, addressed by
  [PR #812](https://github.com/semantica-agi/semantica/pull/812), merged July 29.
  Its merge `ecd0a26a` is already an ancestor of the pre-sync fork, so it is not
  a new Oxigraph sealing fix.
- [Issue #2199](https://github.com/semantica-agi/semantica/issues/2199), open:
  community report reuse is lost when positional community IDs move. Proposal
  uses membership/edge identity. Third-party experimental branch, not merged.
- [Issue #2200](https://github.com/semantica-agi/semantica/issues/2200), open:
  bounded parallel independent community reports; also third-party, unmerged.
  Do not import either experimental branch as a proven performance fix.
- [Issue #333](https://github.com/semantica-agi/semantica/issues/333), closed:
  broad deduplication candidate/scoring/clustering epic, not an implementation
  of the fork's qualified-fact publication/sealing owner.
- [Issue #1436](https://github.com/semantica-agi/semantica/issues/1436), closed:
  cap ontology graph reads and batch external node hydration; applies to an
  Explorer endpoint, not the observed native publication sealing stage.

Searched upstream issues (all states) for performance, Oxigraph, reconciliation,
bulk and slow, then read relevant linked issues/PRs. No matching direct fix for
the current fork-only sealing owner was found in that search scope. This is not
an assertion that every issue in the repository was exhaustively reviewed.

## Verification and limitations

- Main affected suite: **1,111 passed, 17 skipped, 30 subtests passed** in 12.96 s.
  Includes graph access-count/scaling, causal/context active views, provenance,
  exports, parsers, TOML, server/fresh build, triplet filters, vector score/filter
  semantics, PDF owner, extras and Python policy. This run precedes the final
  fail-closed credibility adaptation; its final owner tests are recorded below.
  Evidence: `/tmp/semantica-upstream-sync-20261109-tests.log`.
- Default/None/selected/empty PDF and Python policy: 16 passed after adapting
  upstream mocks and materializing Dockerfile from sparse checkout.
- `uv lock --locked`: passed, 468 packages resolved. Initial direct wheel fetch
  hit a gateway timeout; retry succeeded without weakening the URL/hash pins.
- Native/CLI/MCP integration and final credibility checks: **136 passed** in
  37.78 s. Includes actual native pipeline, publication records, qualified-fact
  index, CLI output, MCP causal chains and GC harness tests. Sparse checkout
  initially omitted `semantica_mcp`; materialize the tracked owner and rerun,
  without changing imports or bypassing the tests. Evidence:
  `/tmp/semantica-upstream-sync-20261109-native-tests.log`.
- Full repository suite, all-platform fresh dependency installation, native
  worker relocation, App acceptance and real-scale timing are not run for this
  source sync. Skipped tests are not passes. Installed dependency environment
  does not constitute a fresh installation of every optional extra in the lock.

## Upstream merge assessment

Disposition: reuse incoming fixes; adapt PDF mocks, credibility missing-data
behavior and graph imports; retain current context/temporal native owners and
exclude incompatible snapshot assembly. No second engine or compatibility
reader is introduced. The 0.8/Python floor change must be checked at artifact
qualification before changing any consumer pin.
