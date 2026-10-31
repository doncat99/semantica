# Native snapshot search ownership

- Date: 2026-10-29
- Inspected revision: 1f5d4734a; local upstream reference 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0
- Status: implemented; focused retrieval regressions verified
- Native owners: context.context_retriever.ContextRetriever, vector_store.VectorRetriever

ContextRetriever already owns keyword scoring and explicit snapshot context;
VectorRetriever owns cosine ranking. Neither public snapshot context nor generic
hybrid retrieve implements explicit keyword/vector search over grounded artifact
records. Generic retrieve also enables expansion/fallback and can generate query
embeddings, which violates this caller's explicit-mode contract. Extend the
existing native retriever with public snapshot preparation/search. Projection of
typed artifact records is a necessary contract mapping, not a new scorer.

Remove candidate creation, source admission and evidence ranking from
semantic_query.py. Keep immutable file/digest/manifest admission and wire DTOs
there. Preserve native scores/order, all-provenance source scoping, warm reuse,
negative/retracted fact display and fail-closed embedding-space checks. No model
calls, hybrid rescoring, duplicate graph files or pagination changes.

Consumers: semantic_query_worker, tests/test_semantic_query_worker.py. Acceptance
Case capability-library-prepare / journey-library, delta keep; no gate or baseline
change. New delegation spec must fail before implementation. Full packaged/ESG
acceptance remains outside focused test evidence. Upstream merge: adapt if native
snapshot search changes; retain one scoring owner, remove superseded adapters.

Verification: delegation spec failed before implementation. Query worker,
native snapshot context/search, existing hybrid and grounded context retrieval:
99 passed; additional direct scope/vector-order spec passed (2 new specs total).
Native keyword and VectorRetriever scores/order stay unchanged, including zero
vector similarity; no reranking or implicit embedding is introduced. Preparation
remains bounded to two immutable artifacts and scope is reapplied for every query.
The new context/snapshot_search.py only maps artifact records and vector evidence
overlap; it computes no similarity score. ContextRetriever owns selection and
ranking, semantic_query.py contains file admission and DTO translation only.
This is ownership consolidation, not a claim of deleting all moved mapping lines.
No user runtime data or paid model calls. Artifact publication and App not updated.

## 2026-11-01 correction: keyword query preparation and reuse

Inspected fork revision `706964a264b794657ca0fb3ac7d68295b9d481af` and upstream
`2c6cfefcabe3c02c90df915a8de463d43f5691e6`. Keyword scoring remains owned by
`ContextRetriever._keyword_match_entities`; the existing
`explorer.search_index.GraphSearchIndex` owns candidate indexing. Its ranked
Explorer search has prefix/secondary scan limits and cannot replace the complete
substring contract as-is. Extend that owner with complete OR-substring postings
over whitespace vocabulary, preserving Unicode and punctuation. Prepare its
ranked exact/token/prefix indexes only when ranked Explorer search needs them;
batch rebuild no longer repeatedly inserts IDs into a sorted list.

`context.snapshot_search.PreparedSnapshotSearch` retains the native index in the
existing admitted-artifact preparation cache. ContextRetriever restores publication
order before applying its unchanged scorer and all-provenance source admission.
There is no extra disk artifact, host search database, alternate scorer, query
embedding, truncation to a smaller candidate set, or runtime fallback. Semantic
ranking is unchanged. The wire response limit of 1,000 remains a separate known
limitation; candidate recall is not limited to 1,000.

Keyword requests no longer require/read retrieval vectors. Semantic requests
still require their admitted retrieval reference and verify its bytes. Graph
admission uses direct typed JSON validation without retaining a second raw JSON
tree. SemanticArtifact mention ownership validation now builds one owner lookup
instead of scanning all entities for every mention; duplicate ownership still
uses the first owner and missing/mismatched ownership still fails. Malformed
mention_ids metadata is rejected explicitly.

Regression evidence: indexed keyword results equal exhaustive native IDs, scores
and order for substring, Unicode, punctuation, multiword and missing queries;
index mutations, lazy ranked preparation, source scoping, no-vector/no-model
keyword execution, and semantic tamper checks are covered. The scaling red spec
used 820 metadata reads for 40 mentions before repair, 40 afterward. Focused
native/query/schema/Explorer regressions: 259 passed, 1 excluded because the
environment lacks semantica_mcp (the full selection reproduces that import
failure). This is not a restored compatibility package.

Real ESG source validation: 309,007,000-byte graph, 19,617 entities, 32,882
mentions, 123,229 evidence spans, 188,273 searchable candidates. Complete indexed
results equal exhaustive results and order for ESG (1,170), environment (5,778),
esg governance (4,602), 環境 (0), g (95,825), plus a source-scoped ESG query (10).
Repeated ESG source execution is about 90 ms; an instrumented fresh process
took 11,348 ms including graph admission, preparation and first index use.
These source measurements are not installed-App acceptance. Native artifact
and HTTP validation are recorded separately in the host engineering evidence.

Host consumers omit the retrieval reference for keyword requests and allow a
canceled keyword caller to leave while the existing worker drains and retains
its admitted data/index. Semantic cancellation policy is unchanged. Upstream
merge assessment: retain one GraphSearchIndex and one ContextRetriever scorer;
reconcile lazy index construction and mutation invalidation with future upstream
changes. No new product knowledge layer or persistent search carrier is added.

Further cold-admission profiling identified 484,638 calls to
`StrictModel.validate_id_like_fields`, each visiting every model field. Cache the
static ID-field names by model class; continue validating each record's scalar
IDs, model IDs and ID lists with the same patterns and errors. This caches schema
metadata only, not content or query scope. A red spec forbids visiting an unrelated
payload field; scalar/model/list rejection tests remain green. The expanded
native/query/schema/Explorer selection passes 263 tests, with the same single
missing-MCP exclusion. Full graph parsing and GC still exist; this change does not
disable validation or alter the process GC policy. Final native-artifact/HTTP
timings are recorded in the host evidence document.

## 2026-11-01 correction: remove full graph preparation from cold keyword queries

The preceding warm-only change did not solve first-use latency. The same inspected
fork/upstream revisions above have no persisted form of GraphSearchIndex's complete
substring postings. Extend that native owner with reference-index publication and
reading, rather than building a host search database or a competing scorer.
`GraphSearchIndex.publish_reference_index` emits the canonical JSON unchanged in
format and a `keyword-index` SQLite artifact during the existing artifact build.
Only vocabulary, numeric postings, record IDs, byte ranges and hashes are stored;
no record bodies, second graph, semantic decisions or alternate knowledge layer.
Both artifacts are bound by the existing artifact manifest. The index is derived
and replaceable; the canonical artifact remains the only content owner.

`ReferenceGraphSearchIndex` searches that vocabulary and reads only matched
canonical records and their required entity/evidence/representation dependencies.
It delegates projection to `context.snapshot_search.prepare_snapshot` and scoring,
stable ordering and source admission to ContextRetriever. No substring candidate
limit is introduced. Query requests never parse/validate the entire graph or build
an index. Streaming file SHA admission and per-record range/hash/ID checks remain;
file identity changes fail closed. Missing or incompatible indexes require an
explicit rebuild; there is no query-time reconstruction or fallback. Existing
semantic retrieval is unchanged.

`GraphSearchIndex.index_artifact` is an explicit offline API for already canonical
artifacts: validate once, build a fresh index, leave graph bytes and identity
unchanged, and call no models. It refuses existing output paths or a noncanonical
serialization. It is never called by query. The host can use admitted index ranges
to verify returned canonical IDs/provenance without parsing the whole graph; it
does not use terms/postings to select or score results.

Affected consumers: semantic_artifact_builder, semantic_worker, semantic_query,
SemanticQueryRequest, native/model artifact acceptance scripts, OntoScience build
admission/query/runtime and packaging acceptance. Cold-path red specification
forbids `_load_snapshot`, `_prepare_query_snapshot` and GraphSearchIndex.rebuild;
it failed before implementation and now passes. Persisted/exhaustive equivalence
covers Unicode, punctuation, OR-substrings, scoped/all provenance and stable scores
and order. Additional tests cover graph-byte preservation, reference-only schema,
missing/tampered identities, bounds and hashes. Focused native/query/artifact
selection: 123 passed. Real ESG HTTP measurements and broader validation are
recorded in the host performance document, not inferred from fixture tests.

Upstream merge: reconcile future GraphSearchIndex persistence with this owner,
retaining one candidate index and one ContextRetriever scorer. Do not preserve
parallel formats or read old missing-index artifacts through a full-graph fallback.
Case page-knowledge-graph retains its primary E2E owner and existing gates/baseline;
focused tests are supporting evidence, not complete installed-App acceptance.

### 2026-11-01 ownership correction: native-only record admission

The preceding proposal to let the host consume index byte ranges is superseded.
OntoScience's artifact-records reader and keyword-index test fixture were deleted;
the host treats the index as opaque and only admits manifest/path references and
the returned protocol, project/revision and authorized source scope. It neither
opens native SQLite tables nor duplicates canonical evidence hydration.

The existing ReferenceGraphSearchIndex reader now also admits canonical header,
lineage and source-version catalog records through its one range/hash reader.
Query requests carry current authorized source IDs and material revisions; the
native semantic_query owner rejects stale, missing, added or duplicate sources
before returning hits. Both modes use this source admission. The host rechecks
adoption and membership/versions after the worker responds; semantic retains its
pre-embedding freshness check. There is no new host knowledge model or fallback.

Native regressions cover opaque consumer boundaries indirectly through the host
tests, and directly cover source changes, unauthorized scope, missing catalog,
canonical-header mismatch and corrupt evidence references. Current focused native,
query, kernel, artifact and Explorer selection: 308 passed, 1 deselected (the same
missing semantica_mcp overlap test). This persistence extension belongs to the fork;
upstream GraphSearchIndex does not already provide persistent cold-query loading.
Real HTTP cold/warm timings remain the host evidence document's responsibility.

### 2026-11-01 cold-start dependency correction

The first accepted native artifact still took 17,124 ms at the host HTTP boundary
(15,469 ms in native execution). Profiling the packaged worker attributed
7.394 of 8.164 seconds to imports: importing ContextRetriever initialized
AgentMemory, vector_store, NumPy/SciPy and graph algorithms before a keyword
query. This is unnecessary capability initialization, not graph query work.

Repair the existing context package exports and retriever initialization: resolve
unrelated public classes lazily, load graph/vector/truth/temporal dependencies
only where those capabilities execute, and retain the existing DRIFT function
alias and registry initialization. Context methods and DRIFT retain their own
implementations; their graph dependencies load on execution. No replacement
searcher, model, score or fallback is added. Tests patch graph classes at their
actual kg owners and import token estimation from its community_summarizer owner.

A subprocess red specification rejects vector_store, kg, NumPy and SciPy imports
while importing the worker and executing an empty keyword query. It failed at
AgentMemory's NumPy import and passes after this correction. Public method/alias
and native keyword regressions pass (66 tests). Expanded regressions and complete
relocated artifact/HTTP measurements are recorded in the host evidence document.
Eleven vector/memory environment failures were reproduced with HEAD context
modules loaded from Git objects: missing fastembed produces dimension/zero-norm
errors. They are not accepted as passing tests or fixed by this keyword change.

Merge assessment: preserve the native public exports, callable drift_search alias,
and actual graph/vector/temporal behavior while keeping unrelated initialization
off the keyword startup path. This changes dependency timing, not ownership.
