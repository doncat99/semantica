# Project-scoped native search and complete original-text pagination

## 2026-11-03 query wire admission follow-up

The existing `semantic_query_worker.serve` owner now bounds JSONL input before
parsing (8 MiB UTF-8 frame, bounded character read), and bounds response encoding
before emitting any successful frame (8 MiB, 64 nesting levels, one million
values/keys). Errors retain at most 2,048 message characters. An oversized input
returns an explicit error and exits, so an unbounded remainder cannot become a
second request; a response-budget error leaves the next request usable. No
successful result is truncated. Host serialization and the current wire schema
are unchanged. Native installation/identity admission remains in its existing
query/index owners.

Three red specifications reproduced missing input/output bounds, including
Unicode bytes and response-failure session continuation. The document/query
worker suites then passed 48 tests. A subsequent two-phase regression verifies
source selection followed by hydration with only page source references and a
stable cursor. Relocated artifact acceptance now exercises that same two-phase
protocol across two sources instead of testing only graph queries. Current
artifact rebuilding/qualification remains separate from source test results.
No upstream API or alternate query engine was introduced; reassess the wire
boundary against upstream worker changes when merging.

- Record ID: 2026-11-02-search-scope-pagination
- Date / author: 2026-11-02 / Codex
- Status: partially implemented; product and bounded-access acceptance pending
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not refreshed in this change
- Related records: [native search](2026-10-29-native-snapshot-search.md)

## Reason and scope

Search hydrated whole sources, exhausted all pages before responding, and used
unbounded text identifiers. Original-text search must return one native chunk per
hit, complete pagination, literal matching and precise original-source locations.

## Native capability assessment

- Owners inspected: explorer/search_index.py::GraphSearchIndex,
  semantic_artifact_builder.py::_text_windows and _docling_locations,
  semantic_query.py, context/context_retriever.py::search_snapshot,
  context/snapshot_search.py::rank_evidence, vector_store/faiss_store.py.
- Callers inspected: semantic query worker, artifact publication, OntoScience
  query.ts/runtime.ts and search route. Tests: test_semantic_query_worker.py,
  test_document_keyword_search.py, test_pdf_reader_ownership.py.
- Decision: extend existing native keyword index and chunker. Keep search and
  locators in Semantica; the host receives an opaque index and paged results.
  No host search database or duplicate PDF parser is introduced.

## Approach and actual changes

- Keyword reference index v2 includes original chunks, postings and parser
  locations. Queries hydrate a single requested page without reading graph or
  parsed-source files. Stable bounded IDs, exact totals and continuation offsets
  replace document collapse and all-page draining.
- Unicode match offsets map to original characters. Native PDF locations reuse
  the PDFParser page join order, including empty pages.
- Offline native reindex accepts verified canonical parsed-source references;
  it does not rewrite graph bytes or call extraction/embedding providers.
- Planned but not implemented: independent parse-stage keyword publication,
  persisted semantic vector index and repeated-query embedding cache.
- Stored-data impact: keyword index v1 requires explicit publication; no v1
  query fallback. Host admission does not reindex at startup or during a query.
  A missing index is an explicit unavailable condition, not a successful search.

## Verification and limitations

- Previous continuation: native query/kernel tests passed; new native PDF page
  location specification reproduced missing locations. Final checks pending.
- Packaged App, real ESG timing/recall, semantic performance and whole-flow
  acceptance have not passed for this change.

## 2026-11-02 bounded-access review

The new original-text page is an output bound, not proof of bounded input.
`ReferenceGraphSearchIndex` still hashes the whole index at cold admission,
loads all representation records for its catalog, scans vocabulary for literal
candidates and performs unbounded count/window/PDF-match-index work. Literal
phrases spanning non-overlapping chunks also need a recall specification.
Semantic retrieval still loads canonical/vector JSON and prepares full ranking
inputs. These defects remain open; no FAISS persistence/query-cache improvement
is claimed by this record. An unfinished FAISS prototype was removed rather than
shipping another unverified retrieval path or restoring a NumPy fallback.

Native query/document/search focused checks in the preceding continuation:
88 passed. Artifact/PDF-ownership focused checks: 65 passed. Those results predate
this documentation correction; they do not qualify the remaining access paths.
The host's current query/runtime/session selection passes 81 tests. Both diffs
pass whitespace checks. No real ESG full-data validation or reindex was run in
this continuation.

The host repository now requires explicit human confirmation before implementing
or executing full traversals, including native dependencies, tests and indexing.
The current host performance record contains a concrete, pending proposal for a
single exact ESG revision, with source/input/output/RSS/time ceilings and no
formal-profile writes. There is no grant recorded. Do not restore automatic
index preparation, run full-index hashing as acceptance, or use a cache/worker
boundary to claim this requirement is satisfied.

## Upstream merge assessment

- Disposition: pending; incoming upstream not reviewed.
- Reassess persistent search owner and chunk/page locators on merge; remove fork
  extensions when upstream supplies the same behavior. Verify literal recall,
  scope, pagination, source locations and no-model-call keyword behavior.

## 2026-11-02 continuation: project reads and indexed vocabulary

Correction: the earlier full-traversal approval paragraph misinterpreted the
host requirement and is withdrawn. Authorized index publication, migration and
integrity verification may traverse their defined scope without a separate scan
grant. Demand-driven queries still must not load entire data sets to answer a
page, and maintenance must enforce memory, cancellation and recovery bounds.

The current native reader hydrates only the canonical header and returned source
representations. Index format v3 adds 1/2/3-character vocabulary grams; literal
term candidates use indexed gram lookup before exact substring verification.
The existing GraphSearchIndex remains the sole publisher and reader owner.
No host index, model call or query-time index construction is introduced.

Regression evidence: 90 native document/query/snapshot-search tests passed.
Vocabulary candidate parity covers Unicode, short and substring terms;
EXPLAIN QUERY PLAN contains no vocabulary SCAN for these lookups.
This is not a claim that the entire query is bounded: whole-index admission,
document body copies, chunk rather than occurrence totals, window/OFFSET
pagination, boundary recall and semantic vector loading remain unresolved.

## 2026-11-03 continuation: positional publication and persistent vectors

Inspected native owners at base `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`:
`GraphSearchIndex`, `ReferenceGraphSearchIndex`, `SQLiteVecStore`, and
`ContextRetriever.search_snapshot`. Their callers are the artifact builder and
semantic query worker. Changes extend those owners; the host does not publish
an independent search index or score results.

The current reference index stores original occurrence positions, Unicode term
grams, canonical byte ranges and record digests instead of document bodies.
Literal phrases cross chunk boundaries; repeated occurrences retain separate
positions. Forward, reverse, source and page navigation use stable positions.
Cold admission requires a stat-bound digest-verified installation receipt;
query-time whole-index hashing and catalog hydration have been removed.
Actual canonical ranges remain checked against their published digests.

The existing SQLiteVecStore persists vectors once, with ID-only evidence/source
group links. Publication batches 128 vectors. Queries admit source filters
inside native retrieval, retain bounded candidate pages and hydrate canonical
records by returned ID. The full graph/vector JSON query and NumPy ranking
path is removed. Retrieval metadata contains only the embedding space.
The host's bounded embedding-query cache binds actor, project, immutable input,
index digest, model and dimension; its TTL is ten minutes.

A real ESG query exposed SQLite choosing a full occurrence-table scan despite
indexed candidate terms. A red EXPLAIN regression now requires candidate-first
indexed posting seeks; CROSS JOIN and INDEXED BY enforce this without depending
on database statistics. Exact totals and original recall remain unchanged.

Offline scratch-only ESG evidence: 38 parsed sources; independent original-text
check found 304 literal ESG occurrences in 18 documents. Seven pages reproduce
every position. Publication took 73.53 seconds, produced 359,133,184 bytes and
peaked at 1,317,650,432 bytes RSS. Native two-phase selection/hydration took
27.47–28.90 ms for the first 50 occurrences, reading 722,901 canonical bytes.
Reopen is not an OS-cold-disk measurement or an App latency measurement.
No formal artifacts or adoption were modified; no model was called.

Verification: six native suites passed 223 tests; subsequent query-worker suite
passed 30 tests including publication batches [128,128,1], reopen and source
isolation. Host query/runtime/membership/content-version/object-store suites
passed 112 tests. Whole-repository checks, current immutable artifact, primary
App acceptance, real semantic latency, and restart/build/token qualification
remain open. Exact counts still visit matching postings; common-term and deep
navigation costs need separate measured evidence. No release qualification is
claimed. Upstream merge disposition remains pending; reassess these native
extensions against incoming upstream owners before retaining them.

### Real-data publication correction

Real ESG vector publication exposed a SQLite reader/writer lock conflict that
small fixtures did not trigger. Publication joins now use an automatically
removed disk scratch database; the native vector store is the only writer to
the published index. Payload batches remain 128 and no canonical text is copied.
The regression includes 2,000 candidates sharing evidence and 257 vectors.
Grouped top-k now retains a sorted, bounded frontier instead of repeatedly
scanning the complete retained frontier for duplicate or losing candidates.

Scratch ESG verification reused 2,994 already-paid 2,048-dimensional vectors,
without provider calls. Publication completed in 21.12 seconds; three reopened
queries returned the same 12 results in 83.95–90.07 ms and read 15,505 canonical
bytes. Foreign-source admission returned no results. The query vector was an
existing document vector: this is persistence/performance evidence, not an ESG
query relevance or App acceptance result. The verification process peaked at
2,164,801,536 bytes, above the proposed 2 GiB publication budget; memory
qualification remains open and this result does not satisfy that gate.

### 2026-11-03 bounded publication and shared-evidence verification

The verifier now parses the canonical graph before loading paid vectors, avoiding
overlapping transient JSON allocations. The same 2,994-vector publication passed
external 2 GiB / 600-second supervision: 305.03 seconds, process peak RSS
979,517,440 bytes (external sampled peak 977,633,280). Three reopened native
queries took 110.26–142.11 ms and read 15,505 canonical bytes; foreign scope
returned zero hits. These are offline results with an existing document vector,
not a model-generated ESG query or packaged App acceptance.

The 2,000-candidate shared-evidence case exposed repeated per-link authorization
inside grouped KNN. The native SQLite owner now uses an ID-set exclusion and
aggregates each bounded KNN batch before checking group admission. Only batch
top-k groups cross into Python; the merged frontier remains bounded by top_k,
with stable ties and no recall truncation. Vector-store and query-worker suites
passed 70 tests, including the fanout publication/reopen case. The 10-second
query deadline is unchanged. Complete frozen-artifact, host and App gates remain
separate requirements.

### 2026-11-03 follow-up: shared-evidence SQL work and timing

The previous grouped-query improvement still enumerated vectors through every
vector/group link and sorted shared associations to compute each group's minimum
distance. The existing `SQLiteVecStore.search_groups` owner now enumerates native
vector IDs directly and finds each candidate group's first matching vector in
the distance-ordered, bounded batch. Source admission remains before KNN/result
limits; tied frontiers are still consumed and only top-k groups enter Python.
No body, entity or evidence store was added, and the 10-second deadline is unchanged.

A red specification measures SQLite VM instructions for 257 vectors sharing
2,000 groups: the original query used at least 21,970,000 instructions and failed
the 12,000,000 ceiling. The repaired owner used at least 2,390,000 instructions,
returned 1,000 groups in 336.84 ms on a reopened fixture, and rejects foreign
source scope. VM instructions are a lower bound at the progress-handler interval,
not a measurement of scanned rows or SQLite disk bytes. Vector-store and query
worker suites passed 71 tests; the two fanout publication cases passed separately.
Logs are in the host workspace under `.tmp/search-shared-evidence-instructions-*.log`
and `.tmp/search-native-query-final.log`. These are focused native results, not
packaged App or semantic-relevance acceptance.

Native query responses also expose bounded numeric timing/read metrics; the host
validates a fixed whitelist and correlates them with its request ID. Keyword
does not acquire vector dependencies. Formal immutable publication/pin and real
App/restart/token verification remain open. This repairs the existing native
SQLite vector owner; reassess the extension against upstream changes rather
than retaining a parallel retrieval engine.

The combined native Keyword, offline publication, wire-worker and vector-store
regressions subsequently passed 151 tests (`.tmp/search-native-combined-final.log`
in the host workspace). Offline publication assertions compare inode, size,
nanosecond modification time and change time; access time is intentionally
excluded because a read may legitimately update it. These assertions still
reject canonical file replacement or modification. This does not qualify the
published three-platform artifact or the real App.

### 2026-11-03 correction: sparse grouped-distance lookup

Native assessment at fork `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`:
`ReferenceGraphSearchIndex.semantic_matches` delegates to the existing
`SQLiteVecStore.search_groups`. Its correlated distance subquery was efficient
for completely shared evidence but scanned the bounded vector batch again for
each sparsely linked group. A reopened 256-vector / 4,096-group red specification
used at least 6,070,000 SQLite VM instructions and failed its 2,000,000 ceiling.

The same owner now joins the bounded batch to the indexed vector/group links
once and aggregates minimum distance and publication position per group. It
retains pre-ranking source admission, exact cosine scores, tied-frontier
continuation, bounded Python top-k, disk scratch and the 10-second deadline.
No index schema, canonical content, retrieval fallback or second engine was
introduced. Callers and wire fields are unchanged. The sparse regression and
existing 257-vector / 2,000-shared-group regression both pass; vector-store and
query-worker suites pass 72 tests.

A read-only replay of the actually adopted ESG index (revision ending
`65498bbd2312410d1a3ef47dc85530b2b97c924717d0d68a89e69dfb38a888b7`)
using one existing stored vector fell from 2.797 seconds to 0.201 seconds.
Grouped SQL fell from 2,638.53 ms to 30.16 ms; 12 hits still hydrated 18 records
and 15,505 canonical bytes. This is offline native evidence, not a model-generated
ESG query, relevance evaluation or packaged App acceptance. Evidence lives in
the host ignored `.tmp/search-group-aggregation-tests.log`; App qualification
requires a newly built immutable native artifact. Upstream merge assessment:
keep this repair in the existing SQLite vector owner and reassess it against
upstream grouped retrieval; do not retain the replaced correlated query.

### 2026-11-03 correction: native imports and physical text locators

Inspected native owners at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`:
`vector_store.__init__` eagerly imported unrelated providers during SQLite
startup. Public exports now resolve lazily; subprocess regressions verify that
SQLite does not import decision pipelines or alternate providers and that the
existing callable `hybrid_search` export survives package/submodule collisions.
This changes import scope, not retrieval semantics or provider selection.

`semantic_artifact_builder._docling_locations` previously inferred offsets from
line text rather than the canonical Docling serialization. It now uses native
`PlainTextDocSerializer` parts/spans, checks exact canonical text identity and
uses native item-relative provenance for multipage items. Invalid charspans
remain unknown; no page is guessed. Serialized table ranges locate matches,
while existing cell records supply model context without duplicating whole
tables in prompts. Content-bearing tables with child groups are visited before
their children; a red native-document regression reproduced the former omission.

Read-only comparison against 304 existing ESG occurrence positions now resolves
all 304 pages from native provenance, including 87 previously missing pages;
three previously assigned pages differ and still need product/source validation.
The diagnostic mirrored the installed artifact's table-serialization environment;
this is not a substitute for an inventoried artifact rebuild and App acceptance.
Fixtures now use the native serializer, preserve formula original-text metadata,
and verify that already-paid extraction context plans remain reused without
model calls. No PDF reader, document copy or alternate locator engine was added.

The focused suite including the child-table correction passed 233 tests in
79.16 seconds. Immutable publication/pin, final App timings,
rebuild token proof and primary acceptance remain unqualified. Upstream merge
assessment: keep exports at the existing package boundary and locator projection
at the existing canonical builder; reassess against upstream serialization API
changes, never retain a guessed-position fallback.

### 2026-11-03 packaged rebuild correction: multipage structural references

The newly packaged ESG rebuild failed in `_structural_evidence`: extraction
retains a whole Docling item reference, while multipage locator projection kept
only page-suffixed character ranges and a coordinate-free whole-item record.
The existing `_docling_locations` owner now retains the exact whole-item range
from the native serializer alongside its page spans. Whole-item citations have
canonical character coordinates; their page remains unknown when it spans pages.
No validator was weakened, page guessed, paid result discarded or model called.
The native document regression reproduced the failure before the repair; the
locator and structural-evidence selection passes six tests after it. A new native
artifact and real ESG rebuild are required before claiming product acceptance.

### 2026-11-03 correction: semantic original-document search

The Explore caller now explicitly requests the existing document target in both
search modes. Previously semantic queries selected knowledge records, which the
host incorrectly presented as original-document hits. The native
`SearchIndex.semantic_chunks` delegates to `SQLiteVecStore.search_chunks`, with
source filtering inside KNN selection before top-k; no host ranking, full JSON
vector matrix, second knowledge store or copied document body is introduced.
Selected canonical document ranges are authenticated and hydrated on demand.
The worker rejects occurrence paging for semantic ranked ranges, validates the
embedding space, and keeps knowledge-target consumers on their existing path.

Native focused coverage passed 165 tests; host query coverage passed 33 tests.
Relocated model-path acceptance now additionally exercises two-phase semantic
document selection and exact original text hydration using its existing loopback
embedding fixture. This check was initially placed in the deterministic fixture,
which intentionally publishes no embedding space; the native artifact gate
caught that fixture error. It is moved to the model-path owner rather than
fabricating vectors in the deterministic build or weakening validation. The
standalone relocated model acceptance passes, including semanticOriginalRanges.

Real ESG acceptance with the new App remains open. The previous App's semantic
cold request exceeded the unchanged three-second gate and returned the wrong
target; neither warm speed nor fixture success qualifies relevance or final
delivery. Upstream merge assessment: retain document retrieval in the existing
native search/vector owners and reevaluate against upstream APIs, without
preserving an alternate ranker or compatibility path.

### 2026-11-03 audit: semantic range location admission

At main `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus the recorded dirty
search implementation, `_query_semantic_documents` only looked up a location
containing the chunk's first character. Real ESG selection 74695..74720 begins
with two serializer newlines; its exact native span 74697..74720 has PDF page
38. The point lookup therefore loses a known page. Repair belongs in this
existing native range-hydration owner, not host-side page inference. Use at most
two indexed location candidates (predecessor and first following start inside
the selected range), retain the first intersecting span, and never borrow a
nonintersecting page. Original text and range identity remain unchanged.
Regression covers leading separators, multiple pages and no intersecting span.
This entry records the repair requirement; verification is appended after runs.
