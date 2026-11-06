# G1 native persistence capability audit

- Record ID: 2026-11-03-native-persistence-g1-audit
- Date / author: 2026-11-03 / Codex native-owner audit
- Status: verified-in-stated-scope; G1 integration acceptance NOT passed
- Fork base inspected: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
- Upstream comparison: local merge-base `0a2731c8223426efaa0dd9e9b345a8411ff3d4f0`
- Scope: OntoScience and its Semantica dependency only. No other project's data or consumers inspected.

## Reason and scope

Determine whether removing fork checkpoint/snapshot aggregates can reuse genuine
native durable owners, without renaming the aggregate or inventing a second
knowledge database. This change adds only a no-model/no-network capability test
and this record. It does not select or implement a new product schema.

## Native capability assessment

| Native owner | Reusable capability | Concrete limitation / decision |
| --- | --- | --- |
| `graph_store/graph_store.py::GraphStore` | Property-graph nodes/relationships, property filtering and limited reads | Neo4j requires a Neo4j service; FalkorDB requires a Redis/FalkorDB service; Neptune requires AWS service; AGE requires PostgreSQL+AGE. None is an embedded local provider. No native SQLite GraphStore source exists. |
| `triplet_store/oxigraph_store.py::OxigraphStore` | Genuine upstream embedded persistent RDF store; named graphs, SPARQL FILTER/ORDER/LIMIT, durable batches | Unchanged against merge-base. Optional `pyoxigraph` dependency. Candidate for reuse, NOT an already-integrated qualified fact owner. Generic Triplet roundtrip drops confidence/arbitrary qualifiers/evidence metadata; explicit RDF statement/provenance mapping is needed. No new product RDF model was defined here. |
| `context/context_graph.py::ContextGraph` | Native graph computation and node/edge metadata | Keeps every node/edge in memory; `save_to_file`/`load_from_file` are whole JSON serialization/loading. Replacing snapshot with this file does not meet bounded durable reads. |
| `kg/knowledge_graph.py::KnowledgeGraph` | Native entities/relationships result object | Lists in memory; no durable bounded storage API. |
| `semantic_extract/cache.py::ExtractionCache` + `SqliteCacheBackend` | Durable extraction-result reuse; execution-policy key invalidation by model/recipe | NOT formal fact storage. TTL, LRU, clear/eviction, and contained storage failures permit misses. Only entities/relations/triplets extraction namespaces; no authoritative source/fact lifecycle or bounded final knowledge API. Do not move finalized facts or graph into cache values. Fork content-policy removes model/recipe parameters and must not be used to claim required invalidation. |
| `provenance/storage.py::SQLiteStorage` | Durable evidence identity, source locator, ranges and metadata; primary-key `retrieve` | Not typed fact storage. `retrieve_all` is unbounded; descendants scans all entries before traversing. Reuse identity reads; repair native list/fanout APIs where needed. Optional quote must not become a duplicate full document. |
| `vector_store/sqlite_vec_store.py::SQLiteVecStore` | Native durable vector backend and ID reads | Generic `search(filter=...)` filters auxiliary metadata after global KNN, losing valid project results. Native-owner repair required. Fork `search_chunks`/`search_groups` extensions are not upstream functionality merely because they use SQLite. |
| `kg/community_hierarchy.py` | Native clustering/hierarchy algorithms and serializable IDs/membership | No durable bounded community/topic record store. Reuse computation; representation and storage binding remain part of G1, not another clustering algorithm. |

Sources/parsed representations also need one chosen native document content
owner and stable source/revision/range identities. Neither extraction cache nor
ContextGraph file is proof of that owner. Current `SemanticArtifact` aggregate
and its custom assertions/communities/topics are fork extensions, not upstream
persisted records.

## Minimal alternatives and remaining design boundary

1. Reuse native **Oxigraph** as the local persistent fact owner, if the approved
   contract can be represented losslessly as RDF statements and provenance.
   Extend the existing TripletStore/Oxigraph owner, not a parallel SQL database.
   Require explicit source/revision scope, qualified assertion identity,
   evidence locators, community/topic membership, bounded reader/update APIs,
   atomic publish/retract and actual query-plan/resource evidence. Product RDF
   schema is a design decision, not authorized by this audit test.
2. Reuse an existing native server GraphStore only if the product explicitly
   accepts an additional database service. This changes desktop deployment and
   is not a drop-in embedded option.
3. If neither meets the product contract, record the missing native capability
   and repair the selected native owner. Do not keep the aggregate as fallback,
   relabel cache as canonical storage, or add a custom second knowledge DB.

Even a storage engine passing capability tests does not mean G1 passes: current
build/query/report/graph consumers still need a single lossless owner and bounded
protocol. Deleting their old producer first would destroy supported behavior.

## Approach and actual changes

- Added `tests/test_native_persistence_audit.py`: independent writer/reader
  processes, temporary directories, synthetic source identities, no models.
- Tests document current limitations deliberately; a green limitation probe is
  NOT acceptance of post-KNN filtering or dropped assertion metadata.
- No production, dependency manifests, user data, extraction results, or host
  contracts changed by this audit. An optional dependency may be installed into
  the ignored audit venv solely to execute the native capability test.

## Verification and limitations

- `.venv/bin/python -m pytest -q tests/test_native_persistence_audit.py`:
  initial run **2 passed, 1 skipped** (PyOxigraph not installed at that time).
- Verified cross-process extraction result persistence with model/recipe cache
  misses and evidence source/range/revision persistence.
- Verified vector primary-key read and unfiltered KNN after restart; reproduced
  generic filtered search returning zero despite a qualifying vector.
- Oxigraph final run and its exact result are appended below when available.
- No ESG product acceptance, packaging, token benchmark or data migration run.
- No production consumer removal implemented; G1 remains unpassed.

## Upstream merge assessment

- Disposition: keep test as capability evidence, adapt when native APIs change.
- Incoming upstream reviewed: local merge-base above; no claim of remote latest.
- Oxigraph source is unchanged against that comparison. Cache content policy
  and vector grouped-query additions are fork changes and must remain explicit.
- Re-run cross-process tests and consumer contract tests after upstream merge;
  do not preserve a limitation assertion after repairing that native defect.

## Dated follow-ups

2026-11-03: installed native optional extra `pyoxigraph==0.5.13` into ignored
`.venv` using `uv pip install --python .venv/bin/python 'pyoxigraph>=0.5.0'`;
dependency manifests untouched by this audit. Final test run:
**3 passed in 1.30s**, no skips. `git diff --check` passed.

Oxigraph demonstrated, across independent processes: named-graph project scope
before LIMIT; stable string-identity continuation; complete standard RDF
reification plus PROV evidence reference and typed generation timestamp filter;
atomic native SPARQL update; rejection of malformed multi-operation input with
no partial insert; durable replacement; withdrawal without touching another
project. RDF temporal provenance in the test is not a substitute for the
product's domain qualifiers. Engine capability is proved, product mapping is
not. The test reaches `OxigraphStore.store.update` because the existing wrapper
does not expose an update method; a production caller would need an extension
of the native wrapper, not direct backend leakage through the host.

G1 remains **unpassed**: there is no approved lossless product mapping for
qualified assertions/source revisions/community/topic membership and no bounded
consumer integration or measured large-data storage reads. This is a concrete
schema/owner decision to resolve, not an absence of an embedded native engine.

### 2026-11-03: concrete field disposition for G1 discussion

This section is a **proposal for discussion, not an approved new RDF schema**.
It uses the actual `SemanticArtifact` and nested models inspected today.
“Lossless” applies to necessary source-grounded facts and user/audit state,
not to preserving every invented aggregate field. Serializing every former
object into an RDF JSON literal would merely rename the forbidden knowledge
layer and is explicitly rejected.

| Existing fields | Required disposition | Native mapping / unresolved gap |
| --- | --- | --- |
| `SemanticArtifact.protocol/snapshot_version/snapshot_id`, whole collections and aggregate JSON | Delete this stored envelope and its snapshot publication/reader contract. No complete replacement envelope | Native records are scoped by actor/project and real source revision; small processing receipts bind recipe/input identities. No graph-wide serialized knowledge version is required to read a source or search one page. |
| `DocumentRepresentation.id/source_id/material_revision_id/input_revision/content_hash/parser/parser_version/recipe_id/recipe_digest/origin/artifact_ref_id` | Keep identity/provenance metadata, without duplicating document bodies | Original source bytes remain immutable material. One Docling structured representation is the parsed content owner. PROV entity/activity/source derivation can bind representation digest, parser and processing recipe. Source-id and project membership authorization stay with the existing host owner. Current wrapper does not provide this exact mapping. |
| `DocumentLocator.representation_id/origin/start_char/end_char/page/bbox/table_id/cell/slide/section_path/quality` | Preserve genuine location coordinates; remove `quote` as a second persisted body | Native Docling refs plus item-local span/table-cell/page provenance should anchor evidence. ProvenanceEntry has source/location/start/end/metadata, but structured bbox/cell/ref needs a specified typed current contract; RDF/PROV alone does not define PDF coordinates. Global plain-text offsets are serializer-dependent and cannot silently become Docling item offsets. |
| `EvidenceSpan.id/representation_id/locator/origin/confidence` | Keep stable evidence identity only where referenced; no duplicated quotation | Use native provenance entity/derivation and located source range. Optional confidence/origin are explicit assertion/provenance properties, not inferred defaults. `EvidenceSpan.quote` and locator `quote` are duplicated with one another and canonical text; read quotation on demand. Check integrity using range/record digest, not full-file reads per query. |
| `KnowledgeEntity.id/canonical_name/type/aliases` | One native canonical entity identity, labels/types/aliases | Reuse semantic_extract Entity plus existing native dedup/resolution result. RDF resource with type/label/alias or native GraphStore entity node; do not write both mentions and entities as full repeated descriptions. Alias needs precise semantics; do not equate every alias using owl:sameAs. |
| `KnowledgeEntity.description/context/attributes/metadata/status` | Retain only admitted semantic facts or genuine user review state | Delete copied raw context; generated description must have a live consumer and support. `attributes`/`metadata` are not permission for an unbounded JSON bag. Extract typed properties into the single selected native owner or remove unconsumed fields. Candidate/accepted/rejected/retracted review state must not be confused with extraction cache hit status. |
| `entity_mentions` and `IdentityRegistryEntry.mention_id/entity_id/source_ids` | Preserve mention-to-entity identity only once, by source/item/span | Native resolution output is the owner; mention is a located occurrence linking an entity, not another entity body. `canonical_name/type` repeated in registry are removed. `unresolved_candidate_count/unresolved_candidates` are bounded review query results; persist actual unresolved decisions only when there is a review consumer, not sampled display lists. |
| `KnowledgeAssertion.id/subject_id/predicate/object/object_entity_id` | Preserve one typed statement; object entity vs literal must stay distinct | Native Triplet can express SPO but `object: str` alone loses int/float/bool identity and nested objects. RDF typed literals express scalar types; reified/quoted statements retain statement identity. Existing `KnowledgeAssertion.object: Dict` must be audited per actual producer: domain structure requires a typed approved model or explicit rejection, never `str(dict)` or one opaque JSON snapshot. |
| `KnowledgeRelation.id/source_entity_id/target_entity_id/type` | Same statement owner as assertions when representing the same fact | Avoid storing an entity-valued assertion and independent relation for the identical qualified fact. Native relation extraction/resolution supplies identity; graph edge is a bounded query projection of that statement. Distinct real predicates/facts must not be deduplicated merely because endpoints match. |
| Assertion/relation `qualifiers` | Preserve polarity and any present condition/time/unit/value without reinterpretation | Current validator permits only these five keys, requires positive/negative polarity and non-empty strings otherwise. Plain SPO cannot represent negative/conditional facts safely. RDF statement-local annotations or native GraphStore assertion nodes can; PROV generation time is NOT domain fact time. Existing Triplet arbitrary metadata is lost by Oxigraph conversion. Native owner schema extension and roundtrip tests required. |
| Assertion/relation `evidence_ids/support_ids/status/metadata` | One set of typed support links and actual review state | Current two support lists need consumer audit before coalescing; do not assume equal meaning. Statement-to-evidence edges preserve many supports across sources. Preserve contradiction/withdrawal distinctions. No copied evidence body or recalculated support on host reads. |
| `SourceRelation.*` | Delete stored transitive/summary links when derivable solely from entity relation support | Query real statement support by selected sources with bounded indexed joins. If a source-to-source relation is independently extracted evidence-backed content, retain that fact with its own identity. `entity_relation_ids`/`evidence_ids` as complete cached arrays are not a reason to persist a second topology. Consumer must state which semantics it needs. |
| `KnowledgeCommunity.id/level/title/entity_ids/relation_ids/parent_id/metrics` | Reuse native community hierarchy; persist only necessary algorithm output and membership, not member body copies | Membership edges and native hierarchy parameters/input dependency bind a reproducible derived result. Titles are names from native output; metrics only if consumed. Full member ID arrays become indexed bounded membership queries. Community is derived organization, not an independent knowledge version. |
| `KnowledgeTopic.id/title/community_ids/entity_ids/assertion_ids/evidence_ids/metadata` | Do not retain a second topic knowledge layer by default | Native topic consumer/capability and independent value must first be demonstrated. If topic is just a community label/member union, delete it and render native community. A user-authored annotation has its existing product owner. No evidence yet to justify preserving every current topic record. |
| `source_classifications/classification_profile` | Preserve only the existing product's real classification contract | Keep canonical class/profile definition once and per-source class assignments as derived results with source/recipe support. Do not persist duplicate full profile per build; do not substitute classes for native communities. Necessary consumer/owner mapping is still unresolved. |
| `KnowledgeConflict.*` | Actual review workflow state may be necessary; automated duplicate fact copies are not | Native conflicts owner supplies conflict detection. Store review decision and references once if there is a current consumer; query supporting facts by ID. Do not copy the full competing facts into a conflict artifact. Native SQLite provenance is insufficient proof of this workflow owner. |
| `KnowledgeReport/ReportSection` | Keep user-requested report as product output in existing report owner | Report prose is generated content, not source plaintext duplication. Keep source/evidence references and generation receipt. Do not insert report prose back into canonical facts or create per-build reports nobody requested. |
| `RetrievalArtifactManifest` lists and full retrieval JSON | Delete duplicated whole-vector/whole-record envelope | Native VectorStore holds vectors once; small embedding-space identity/config, index recipe and source revision bindings suffice. No complete entity/relation/evidence ID catalog in a manifest. Native query reads hit IDs and then needed records. |
| `ModelReceipt`, `KernelLineage`, `ArtifactManifest` | Preserve minimal audit/dependency identities in actual job/artifact/provenance owners | Keep model/operation/input-output digests/parameters where needed to prove cost and derivation; no model-response/source body duplication. Delete graph/snapshot artifact manifest members with their producers. A digest or source revision is necessary provenance, not permission to recreate aggregate history. |
| Arbitrary `metadata` on all classes | Field-level inventory before retaining | Every key must name its consumer, type, size bound and authoritative owner. Unconsumed keys are deleted. No catch-all sidecar JSON carrying removed snapshots/checkpoints. |

### Unique Docling carrier: exact unresolved reading boundary

Current `parse/document_reader.py::project_document_reader` reconstructs a whole
DoclingDocument, serializes whole text, and stores `chunks[].text`,
`pages[].text` and `pages[].blocks[].text`. `semantic_document_reader.py` indexes
byte locations of those projections inside the same payload. This may avoid an
extra file but still duplicates content within that file; it is **not** the
target unique Docling carrier. `semantic_source_artifact.py::_parse_source` also
places `parsed.text` into `document.text` and checkpoint tuples.

Required replacement, to validate with the document-reader owner agent:

- Retain native structured Docling JSON once, without DocTags, reader text/page
  mirrors, whole plain text or document checkpoint payloads.
- Build a disposable address index while serializing the native representation:
  native item/ref → byte range, digest, native item type; page/table-cell → item
  references and provenance. This is an address/position index, not text storage.
- Read bounded native text/table items by ref, then run native serializer for
  those items and retain its offset mapping. Exact serializer behavior for list,
  heading, table merges and cross-item separators must be proved; truncating a
  full serialization or approximating joins is not equivalent.
- Native JSON can contain one huge table/item. Range support must include typed
  table-cell/row references and sub-item addresses; `json.loads` on a 100MiB item
  merely relocates the full-load bug. Escapes, multibyte text and page provenance
  must roundtrip. Original model allocation during parsing is a separate budget
  from a page query; it does not justify full document query allocation.
- No claim that upstream Docling currently exposes these file-range APIs was
  established by this audit. Semantica owns its integration/address index;
  extend Docling fork only if its native item serializer/provenance is genuinely
  insufficient, with direct contract evidence. Do not add a second PDF reader.

### Derived indexes: permitted fields and forbidden bodies

Keyword postings may hold normalized token/substring grams, source/item IDs,
source-local positions, native-byte addresses, page/cell locators, record digests
and scalar ranking statistics required by the exact matching contract. Unicode
normalization position maps are necessary derived features. They must not store
complete plaintext, escaped full-source strings or cached snippets. Snippets
come from bounded source ranges. Token tables must have measured overhead and
indexed candidates, rather than scanning every token for each substring query.

Vector storage may hold embedding, stable source/item/span ID, embedding-space
identity and typed pre-retrieval project/source authorization filters. It must
not contain body copies or a vector JSON shadow. Community/classification
indexes may retain membership/result identities, not duplicate entity/evidence
objects. All indexes are rebuildable from the selected single content/fact
owners, never independently edited authoritative knowledge.

### Atomic source withdrawal: proposed semantics, not implemented

Source deletion/replacement must withdraw exactly that source revision's
contributions and supports. It must not delete an entity or qualified statement
still supported by another live source. Candidate representation: a named graph
per source revision containing source-owned statements/annotations, plus a
small project membership/catalog owner. Native SPARQL update can atomically
delete that graph's membership and contributions; no complete project graph
needs rebuilding. Shared entity identity must have one native owner, with
unsupported-entity garbage collection scoped by actual references.

Oxigraph/SQLite/vector files do **not** share one ACID transaction. Therefore
an implementation must not pretend sequential writes are atomic publication.
Keep native facts as truth; derived entries carry source identity and queries
must filter live authorized revisions **before** search limit/ranking. A fact
commit can make stale index rows ineligible immediately, with bounded index
cleanup afterward; newly committed source must not report search-ready until
its required indexes are complete. Final native owner protocol must prove
crash windows, visibility, deletion and restart. This small readiness transaction
must never contain stage result bodies or become renamed checkpoint storage.

### Two minimal storage options to discuss

| Option | Concrete implementation boundary | Cost / outstanding acceptance |
| --- | --- | --- |
| **Recommended candidate: native TripletStore + embedded Oxigraph** | Repair existing Oxigraph wrapper for parameterized/current typed fact/provenance reads and native atomic updates; reuse ExtractionCache only for paid-result reuse, SQLiteVecStore only for vectors, Docling for document content. RDF standard statement/provenance semantics plus the smallest approved qualifier mapping, no aggregate snapshot. | One embedded native library, no new service. Mapping for domain qualifiers/source support and bounded community membership still requires explicit review. Large-data query plan, cancellation, actor/project enforcement, single-writer/open lifecycle and cross-store search visibility need proof. |
| **External native GraphStore (Neo4j as concrete reference)** | Existing native entity/assertion/support nodes and typed edges/properties, parameterized Cypher and native transactions. One selected current backend only, not runtime dual backend/fallback. | Adds database service deployment/credentials/lifecycle/backup and desktop availability requirements. Existing transaction owner exists; nested qualifier metadata must use typed nodes/properties, not opaque JSON. No real Neo4j instance was started or validated here. FalkorDB/Neptune/AGE are not embedded substitutes. |

Recommended candidate is not unilateral approval: selecting RDF introduces a
concrete product field mapping and build/query contract change. The user should
see this decision before implementation; G1 cannot be stamped green merely
because the engine test passes.

### Suggested measurable budgets (proposal, no baseline change)

- Normal keyword/reader request: page size 50 default, at most 100; ≤2MiB response,
  ≤8MiB canonical range reads, ≤32MiB additional retained memory. Oversized
  legitimate results require explicit continuation, never silent recall loss.
- Native source item address page ≤256KiB metadata; individual location ≤4KiB;
  table reads by cells/rows so large tables remain accessible.
- Keyword end-to-end first page target p95 ≤500ms warm, ≤1s after restart on
  agreed ESG hardware; query-vector model/network time reported separately for
  semantic mode. Measure queue/admission/storage/hydration/transport/render.
- Native fact page deadline 2s, cancellation observed ≤250ms, bounded hierarchy
  traversal with explicit continuation. LIMIT alone proves neither low scan
  work nor bounded memory; record actual bytes/rows/allocations.
- Build/index traversal: one source at a time unless measured parallel parsing
  budget permits more; native batches ≤1000 facts or 4MiB, whichever first;
  indexer extra memory ≤256MiB, progress/cancellation and safe failed write.
  Whole parser/model RSS needs a separate measured per-platform ceiling.
- Shared query caches ≤64MiB combined per worker, real input-derived keys,
  request cancellation must not evict stable admitted data.

These numbers are proposed acceptance budgets for discussion and measurement,
not claimed performance results or changes to existing Auto Test pass criteria.

### Native dependency evidence and platform checks

Measured installed `pyoxigraph==0.5.13` distribution on this Mac: **15,358,772
bytes** including extension **15,030,608 bytes**; wheel tag
`cp39-abi3-macosx_11_0_arm64`, Requires-Python `>=3.9`. Download progress reported
about 5.6MiB compressed. This is an actual local observation, not an all-platform
package budget; shared runtime/library duplication has not been measured.

Before choosing it for release, verify the precise pinned Python/CPU/OS wheels
for mac arm64/x64, Windows and Linux targets; installation without Rust toolchain;
native extension dependencies/signing/notarization; release license notices;
DB directory lifecycle, locking/single writer and read-only access; interrupted
write/disk-full behavior; packaged artifact size and cold-open memory. Current
ABI3 wheel compatibility does not prove those runtime/platform properties.
Measure package delta against the same complete baseline, not whole app size.

### 2026-11-03: native Docling item/cell/range capability verification

Read-only audit of installed `docling-core==2.103.1` in the fork's `.venv`;
these observations identify the inspected runtime, not the latest remote fork.
Reused the synthetic Docling/provenance construction patterns already in
`tests/test_document_reader_projection.py` and
`tests/test_docling_search_locations.py`. No PDF parsing, models or network.
No production or other agents' tests changed.

**Native API source evidence:**

- `docling_core/types/doc/document.py::load_from_json` (installed line 3844)
  calls `filename.read_text` then `model_validate_json` on the full string.
- `extract_items_range` (3217) resolves children from an existing loaded model
  and copies selected node items into a new DoclingDocument. Its name does not
  imply bounded on-disk range reads.
- `common/reference.py::RefItem.resolve` indexes attributes/lists on an already
  loaded document; it is not a file address resolver. `FineRef.range` gives a
  logical range but does not perform an I/O read.
- `transforms/serializer/common.py::get_parts` (647) accepts an `item` and can
  traverse that subtree; this is reusable serialization capability, but returns
  a list and depends on document-resolved children, captions and rich cell refs.
  Whole-document construction before calling it remains unbounded query I/O.
- `PlainTextDocSerializer` reuses `MarkdownTableSerializer`. Its table path
  (markdown.py 793–884) iterates the full `item.data.grid`, collects all rows,
  computes headers/column alignment and calls tabulate. It emits a span for the
  whole table, not a cell-level transformed-text map.

**No-model experiments and their actual output:**

1. A native two-row Unicode table with cells `头😀` and `行漢`, table provenance
   on pages 1 and 2, serializes to
   `'| 头😀   |\n|--------|\n| 行漢   |'`.
   Native serialization spans identify only `#/tables/0`. TableCell fields
   contain row/column spans and optional bbox, but **no page identity**.
   The same table passed to current Semantica reader returns pages 1 and 2 both
   `invalid_layout`, zero blocks. The reader intentionally only admits a table
   with one provenance item and `(0,0)` charspan; this is a capability gap,
   not justification to guess page/cell locations or repeat the table on pages.
2. A picture with child OCR text `OCR 漢😀 ESG` and genuine text provenance:
   `export_to_text()` returns `''`; native
   `export_to_text(traverse_pictures=True)` returns `'OCR 漢😀 ESG'`.
   Passing the latter text to current `project_document_reader` raises
   `ValueError: native Docling serialization does not match the representation`.
   Its serializer configuration does not preserve the same picture traversal.
   OCR must use the single native serialization recipe throughout; missing
   traversal cannot be patched by copying another text representation.
3. Existing Unicode span fixture uses `A😀B` with item-local `(1,2)` provenance;
   Python/Docling character indexing correctly selects `😀`. A byte-address
   index must preserve the difference between UTF-8 byte offsets and Unicode
   code-point offsets, including JSON escaping. UTF-16 UI offsets require an
   explicit boundary conversion; no such equivalence was proved here.

Focused existing fixture run:
`.venv/bin/python -m pytest -q tests/test_document_reader_projection.py tests/test_docling_search_locations.py`
returned **6 passed, 1 failed** in 1.62s. Failure was
`test_native_reader_preserves_interleaved_table_order_and_unicode_spans`: page
blocks did not contain the expected interleaved emoji item. These source files
are under concurrent remediation; this result records observed workspace state,
not an attribution to a specific commit. No failing fixture was modified here.

#### Minimum interface repairs and proof required (not implemented)

| Owner | Minimum current interface change | Required lossless/bounded proof |
| --- | --- | --- |
| Semantica parsed-source publication / selected native Docling serializer | Publish exactly one native structured document; record disposable addresses for native item refs, cells and page metadata during writing. Document content and parser recipe must have immutable identities. | Unique marker text occurs once across parsed outputs; no document/text/reader/checkpoint mirror. Index contains addresses/digests/features only. Same-content source rebinding adds no parsed-body bytes. |
| Semantica `semantic_document_reader` integration | Replace reading `reader.chunks/pages` projections with bounded requested native `item-ref + local span`, `page + continuation`, or `table-ref + row/cell range`. Enforce bytes, objects, fanout and deadline before allocation. | Deep item read I/O is proportional to selected item/range plus bounded ancestors/refs, independent of preceding document size; huge item/table remains accessible through continuation. Crash/restart retains native addresses and detects changed content without per-query whole-file hashing. |
| Docling core native serializer, **only where existing item API is insufficient** | Reuse item serialization; add ranged/streaming table-cell serialization or a native cell-to-serialized-text span map if the product genuinely requires that representation. Do not reimplement table formatting in host/Semantica. | Merged cells, multiline/pipe escaping, headers, numeric precision, captions, rich-cell references and list nesting preserve native semantics. Table formatting with global column widths cannot be advertised as bounded identical ranged formatting without proof or an explicitly agreed consumer representation. |
| Docling native provenance / conversion, when source provides necessary precision | Preserve page identity for each located cell/fragment in multi-page tables. Existing bbox without page is ambiguous. | Same-shaped bboxes on different pages remain distinct; each evidence quote maps to actual source page/cell. Unknown physical mapping remains explicitly unknown/coarse. No guessed page or duplicated full table fallback. |
| Semantica Docling adapter and all serializer callers | Bind one processing recipe including labels/layers/picture traversal and serializer version. Use actual native OCR item provenance, not PDF text reopened by another reader. | Picture-child OCR text survives parsing, extraction, keyword recall, reader and evidence lookup identically; no extra model call, no lost Unicode ranges; invalid provenance produces typed unlocated state. |
| Host reader/evidence contracts | Specify native ref, item-local code-point span, optional physical page/cell bbox, precision and immutable source/representation identity. Convert display offsets at UI boundary only. | Repeated text, emoji/combining marks, CJK, escaped quotes/backslashes, multi-page items and table cells locate the intended occurrence. Source replacement makes stale locators explicitly invalid. |

The native structured JSON contains enough information for ordinary text-item
identity/content and its supplied provenance, but **does not itself provide a
bounded file reader or prove precise page assignment for every table cell**.
One carrier is viable as a target; its required storage/range and physical
provenance contracts are not complete today. Neither a new knowledge layer nor
retaining redundant reader plaintext resolves those missing native interfaces.

## G1 selected-owner evidence: typed Oxigraph facts (2026-11-03)

The user has selected the existing native Oxigraph owner. The earlier alternatives
above are investigation history, not runtime choices or a proposed provider
fallback. This appendix verifies that selection; it does not introduce a business
writer, a snapshot substitute, or a completed G2 contract.

`test_native_typed_qualified_facts_and_shared_support_withdrawal` now exercises
three independent processes using the selected `OxigraphStore.execute_update`
and `execute_sparql` interfaces. Query inputs use native RDF variable/term
substitutions. Update terms use native `NamedNode`/`Literal` serialization;
unescaped user strings are never concatenated into RDF syntax. Oxigraph 0.5.13
requires substituted variables to appear in the SELECT projection; the fixture
therefore projects its bound project variable explicitly.

### Minimal mapping proved by the fixture

The `urn:semantica:audit:` vocabulary is an experimental fixture vocabulary,
not an approved production schema. These predicates expose individual fields
to native indexed RDF query; they do not carry an opaque JSON object.

| Existing meaning | Native RDF representation / owner | Acceptance evidence |
| --- | --- | --- |
| One qualified fact identity | One `rdf:Statement` with `rdf:subject`, `rdf:predicate`, `rdf:object` in the project's graph | Typed object read after process restart |
| Scalar object | XSD integer, decimal, boolean or string literal | `42`, decimal `12.3400`, boolean false and numeric-looking string `00042` remain distinguishable; decimal numeric equality is tested rather than requiring engine-preserved lexical formatting |
| Entity-valued object | RDF named node, not an entity name copied into a scalar literal | `isIRI` query succeeds; no additional relation object duplicates the same fact |
| Polarity / condition | Statement-local explicit predicates | Negative and conditional fact survives restart; no unconditional positive subject/predicate/object edge is emitted |
| Time / unit / qualifier value | Statement-local literals | `FY2024`, `tCO2e` and lexical `approximately 12.3400` roundtrip separately from the typed object; current qualifiers are strings, so time is not guessed into an invented calendar date |
| Source support | Statement-to-evidence `prov:wasDerivedFrom` link in each source-revision contribution graph, with explicit project association | Two independent source contributions support one fact; removing one source leaves the fact and the other evidence intact after restart |
| Confidence | Per-evidence typed decimal | Independent `0.91` and `0.83` are preserved, with no fabricated merged global confidence |
| Evidence location | Representation URI plus native item ref, item-local Unicode code-point start/end, supplied physical page | `#/texts/7`, independent ranges and page 2 survive restart; no evidence quote/body is stored in this RDF mapping |
| Final support withdrawal | Native atomic update drops that source contribution and deletes the now-unsupported statement fields | Final withdrawal removes the fact; another fact in the project remains |

The current fork `support_ids` are evidence IDs, constrained to a subset of
`evidence_ids`; the relation builder often writes identical arrays. Host code
passes them through but does not supply a separate business meaning. They must
not be interpreted as native truth-maintenance support identifiers. The proposed
single evidence-reference set replaces that duplicated transport meaning.
Where a relation-valued assertion and a `KnowledgeRelation` describe the same
qualified fact, the native mapping stores one statement rather than two fact
objects. This is not permission to collapse distinct polarity, condition, time,
unit, scalar/entity type, or evidence identity.

Evidence quotes have actual downstream uses: model input, recall and repeated-
text disambiguation. Removing stored quote copies therefore requires recovering
the exact content from the **single parsed native carrier** by immutable
representation identity, native item ref and local span. Page/bbox alone is
insufficient. The RDF fixture proves locator persistence; it does **not** prove
carrier range access, quote reconstruction, merged-table cells or OCR location
accuracy. Those remain the parsing/reading owner gates recorded above.

### Verified result and limits

`.venv/bin/python -m pytest -q tests/test_native_persistence_audit.py`:
**4 passed**, 3.11 seconds, no model/network calls and no production data writes.

The wrapper's row/byte caps bound Python result materialization and fail on
overflow instead of truncating results. They do not prove bounded physical
engine reads, sort memory, execution deadline or cancellation. The test's small
fixed LIMIT queries likewise do not establish production performance. No
cross-store transaction with vector storage is established. The pre-existing
vector metadata post-KNN limitation remains an explicitly labelled probe, not
a passing acceptance criterion for the final search contract. G1 cannot be
declared fully complete from these four capability tests alone.

### G1 point-read scale experiment

Added `test_native_project_source_id_point_reads_scale_without_python_materialization`.
Each scale is populated by its own writer process using a generator, followed
by a fresh reader process. The 1,000 / 100,000 record datasets contain two quads
per record: one project-scoped field and one source-scoped field. An additional
foreign-project quad reuses the same target ID with a different value. The
reader executes three exact native RDF substitutions: target ID + project,
target ID + its source graph, target ID + a different source graph. The first
two return their precise fields; the third returns no row. No LIMIT is used as
evidence of bounded physical work. The fixture proxy exposes only native
`query` to the production wrapper, preventing Python-side whole-store iteration
or `quads_for_pattern` enumeration along this measured path.

Observed macOS arm64 results, pyoxigraph 0.5.13:

| Stored records / quads | Native store open | Three point queries | Python peak allocation during queries | Process peak RSS | RSS peak increase during queries | OS input-block delta |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 / 2,001 | 34.61 ms | 36.13 ms | 4,918 bytes | 54,771,712 bytes | 1,343,488 bytes | 0 |
| 100,000 / 200,001 | 76.87 ms | 3.26 ms | 4,918 bytes | 55,476,224 bytes | 1,359,872 bytes | 0 |

Command: `.venv/bin/python -m pytest -q -s tests/test_native_persistence_audit.py`:
**5 passed in 11.55 seconds**. Datasets are temporary and contain synthetic
payloads; no real profile, model or remote service is accessed. The enforced
test bound is less than 1 MiB of Python allocation for these requested fields
at both scales, not a new product latency or native-memory baseline.

This gives direct evidence that the selected point-query wrapper does not
load the dataset into Python, and that this tested access pattern did not
grow query allocations with 100x data. It does **not** prove all native
physical reads are bounded: `Store` 0.5.13 exposes no explain/plan statistics,
row-visit count, RocksDB read-byte counter or deadline/cancellation argument
in its Python query API. `ru_inblock=0` can reflect filesystem/engine caching;
it cannot establish zero bytes read or zero scanned rows. The 1,000-record
latency exceeding the larger dataset also shows why these single samples are
not a performance percentile claim. Native engine sort/scan memory and a hard
query deadline remain unproven. A product query that introduces broad graph
patterns, ordering or an unindexed filter must be reviewed independently;
neither these point reads nor a wrapper row cap proves it acceptable.

## G1 consumer-derived field whitelist and remaining gate (2026-11-04)

This appendix records the approved embedded Oxigraph direction; it does not
declare the consumer migration implemented. The whitelist is default-deny:
an arbitrary `metadata`, `attributes`, object dictionary or serialized record
must not be put into an RDF JSON literal. Each admitted field needs an explicit
predicate, native term type, identity, owning writer and bounded reader. A
consumer reading an entire dictionary today is evidence of a boundary to repair,
not authorization to retain that dictionary.

### Consumer evidence

The current field demand is traceable to these owners (paths in this section
are relative to the named repository):

- Fork `context/snapshot_search.py:90`: builds searchable descriptions from
  entities, assertions, relations, conflicts and topics and associates evidence
  with source representations. Its whole-aggregate preparation must disappear.
- Fork `semantic_worker.py:131`: report targets and source passages consume
  entities/assertions/relations, communities/topics and evidence provenance.
  Reports need bounded target/support reads rather than an aggregate argument.
- Fork `semantic_artifact_builder.py:2057`: emits an entity-valued statement as
  both an assertion and relation. One qualified native statement must replace
  those duplicate models. At `:2215`, topics derive from grounded report
  sections; they are product organization results, not independent facts.
- Host `apps/daemon/src/knowledgehub/semantica/understanding-index-worker.ts:139`
  projects names/types/descriptions/attributes/status, claim values and
  qualifiers, conflict reasons, topic organization and formula expressions.
  `understanding-references.ts:61` also passes support/evidence references and
  source-relation provenance. A projection is not a second durable fact owner.
- Host `report-dependencies.ts:6`, `report-read-model.ts` and
  `reading-reports.ts`: reports require target/evidence/dependency references
  and authored text. Persisted canonical-context copies and collection-wide
  dependency hashing are replacement targets. `build.ts:421` and
  `worker.ts:1161` already reject reports embedded in the graph.

### Complete field disposition

`Facts` below means typed native Oxigraph statements/references; `content` means
the single parsed-document carrier, not an additional quote store. `Index`
means rebuildable native-owner search features that cannot become authoritative
entities, evidence, relationships or a knowledge revision chain.

| Current fields | Owner and minimum retained representation | Fields/output to remove or disallow | Required fidelity / access check |
| --- | --- | --- | --- |
| Representation `id, source_id, material_revision_id, input_revision, media_type, content_hash` | Facts: immutable identity and source/content reference; content bytes exist once in the chosen document owner | No complete representation object in graph, report context or index | Resolve exactly the requested representation; reject foreign source and changed content |
| Representation `parser, parser_version, recipe_id, recipe_digest, origin, artifact_ref_id, created_at` | Typed processing/provenance references; `artifact_ref_id` points to the sole content carrier | No parser-result JSON/text/DocTags siblings; DocTags are no longer requested by the user | Parser/recipe change invalidates affected dependencies without loading document bodies |
| Representation `metadata` | Only individually declared parser/provenance fields necessary for a current consumer | All undeclared keys and embedded document bodies | Explicit producer/consumer schema; missing required field is a typed error |
| Evidence `id, representation_id, origin, confidence` | Facts: evidence identity, representation reference, typed origin and finite confidence when present | No duplicate evidence objects in every fact/report/index | Per-ID and bounded source-scoped retrieval; confidence precision and absence preserved |
| Evidence locator `representation_id, start_char, end_char, page, bbox, table_id, cell, slide, section_path, quality, origin` | Native provenance: carrier item reference plus local codepoint range; typed page/geometry/table/slide/section fields only where necessary | Locator `quote` and evidence `quote` copies; whole structural subtrees | Reconstruct exact cited text from sole carrier, including repeated text, OCR, cells and reading order; page/bbox alone fails |
| Evidence `metadata.role, metadata.structural_ref` and other `metadata` | Whitelist the source-passage role and native item reference actually needed by report/reader consumers | Duplicate `structure` content; unspecified metadata | Source passage and item can be found by bounded native lookup; no body scan |
| Entity `id, canonical_name, type, aliases, status` | Facts: stable entity, typed names/type/status and alias edges | Repeated entity arrays and registry name/type copies | Identity merge/retraction preserves aliases and support; bounded label/type reads |
| Entity `description, context, attributes, metadata.expression` | A verified extracted claim becomes a typed supported statement; consumed native semantic descriptions remain once as bounded typed native text with provenance, regardless of model generation; expression is a typed derived formula with provenance when actually supported | Whole arbitrary attributes/context/metadata dictionaries; copied source paragraphs | Extraction-spec field/type whitelist and consumer audit before admitting each field; no silent conversion to a JSON string |
| Entity `evidence_ids` | One native support edge set | Embedded evidence records or an additional mirrored support list | Shared support survives single-source withdrawal |
| Assertion `id, subject_id, predicate, object, object_entity_id, status` and relation `id, source_entity_id, target_entity_id, type, status` | One qualified statement model: subject/predicate plus typed scalar OR entity object, status and stable identity | Dual assertion/relation copies for the same qualified statement; runtime translation between two models | Preserve boolean vs string vs numeric vs entity; distinguish otherwise equal facts with different qualifications |
| Assertion/relation `qualifiers` | Explicit native predicates for exactly `polarity, condition, time, unit, value`; polarity required; remaining fields retain declared string semantics | Arbitrary qualifier dictionaries, invented defaults, flattening qualifications into an unqualified triple | Positive/negative, conditional, time/unit/value distinctions; absent versus present fields |
| Assertion dictionary `object` | No generic dictionary admission. Decompose only a concrete extraction-spec structure into declared typed fields or reject it as unsupported | Opaque JSON literal, dropped keys or coerced object string | A failing specification for every admitted structured object shape before implementation |
| Assertion/relation `evidence_ids, support_ids` | One evidence support edge set: current support IDs are evidence-ID subsets, not a second truth-maintenance identity system | Redundant arrays / invented independent support records | Preserve existing support membership and withdrawal semantics; do not assume generic TruthMaintenance IDs are compatible |
| Assertion/relation `metadata` and reference `direction` | Admit only individually proven semantics. Direction must be derived from the declared predicate/ordered endpoints | Generic metadata; fabricated `forward` default masquerading as stored evidence | Directed/reversed relationship fixture and explicit missing-contract error |
| Source relation `id, source_id, target_id, type, evidence_ids, entity_relation_ids, status, unresolved_reason` | Typed source-to-source statement referencing the same native entity statements and evidence | Copied entity relationships, independent source-graph body, arbitrary metadata | Cross-source scope and unresolved state retained; referenced statements resolve by ID |
| Identity entry `mention_id, entity_id, source_ids, unresolved_candidate_count, unresolved_candidates` | Mention/evidence-to-entity edges and bounded typed candidate edges/reasons; candidates at most the declared eight | Duplicated `canonical_name, type`; arbitrary identity-profile body or quote copies | Mention locator, merge/split identity behavior, bounded candidates and support-sensitive deletion |
| Community `id, level, title, entity_ids, relation_ids, parent_id, metrics` | Native clustering computes membership; retain product organization title/level/parent and references once. Index only membership needed by current graph queries | A second graph of entity/relation contents; undefined metrics dictionaries | Parent/cycle validity, source withdrawal, bounded member pages; whitelist any actual metric consumer before storing it |
| Topic `id, title, community_ids, entity_ids, assertion_ids, evidence_ids` | Product organization result with native references and supported title; bounded membership index only if consumed | Independent topic fact truth, copied cited bodies and embedded member objects | Grounded title and membership remain traceable to cited evidence; no target-specific hardcoding |
| Topic `metadata.organization` | Exactly typed `basis, report_id, input_digest, coverage`, with currently produced values `grounded-overview-section` and `cited-knowledge-only` for basis/coverage | Generic metadata object, report body copy, new snapshot identity | Report/input references resolve; stale report invalidates derived organization explicitly |
| Conflict `id, conflict_type, status, entity_ids, assertion_ids, relation_ids, evidence_ids, reason, resolution` | Native typed conflict relationships/state and consumed reason/resolution once as bounded typed native text with provenance; model generation alone does not make this a separate product result | Whole candidate/fact/evidence bodies in conflicts; fork conflict evaluation duplicate of native owner | Open/resolved/ignored transitions, referenced claim/evidence validity and source withdrawal |
| Source classification `source_id, profile_id, profile_version, assignments, unclassified_dimension_ids, model_receipt_ids` | Source-scoped typed assignment edges: dimension/item/confidence/evidence and receipt references | Per-source copy of profile or vocabulary, body text | Single/multi cardinality, absent/unclassified dimensions, source isolation and evidence grounding |
| Classification profile `id, version, label, description, dimensions`, dimension vocabulary hierarchy | One processing-configuration owner and digest; results reference it | Copy of full profile inside each knowledge/result record | Configuration change binds a new input dependency, not executable old/new contract dispatch |
| Report `id, report_type, title, summary, entity_id, community_id, topic_id, conflict_id, retrieval_manifest_id, sections.title/text/evidence_ids, evidence_ids, model_receipt_ids, content_hash` | Product report owner: generated/edited text once, typed target/evidence/receipt/dependency references | Report inside graph; duplicated canonical `context`; stored copies of facts/evidence or render compilations that can be regenerated | User edits survive; bounded target support, missing/stale dependency errors and restart recovery |
| Report `metadata.depends_on` | Explicit small per-record/content/recipe dependency references and digests | Full collection copies/hashes recomputed on every read, arbitrary metadata | Changing one consumed fact invalidates the dependent report without enumerating whole graph |
| Retrieval manifest `id, retrieval_type, artifact_hash, artifact_ref_id, index_id, record_count` | Small native index installation/publication metadata bound to project/source/material/model/recipe | Snapshot aggregate manifest; historical knowledge-version chain | Query pins exact installed active index binding and rejects incomplete/stale bindings |
| Retrieval manifest `entity_ids, relation_ids, community_ids, evidence_ids, model_receipt_ids, metadata` | Index lookup tables and typed generation/recipe/receipt references only where required | Whole membership arrays duplicated in manifest; text/body or arbitrary metadata payloads | On-demand index identity and hit record checks, bounded bytes and rows |
| Model receipt `id, operation, provider, model, input_digest, output_digest, created_at, parameters, metadata` | Execution/audit owner: typed identity, finite declared effective parameters, token counts and provider request reference where available | Prompts, full model response, document/fact copies; arbitrary parameter/metadata blobs | Real zero-model keyword and warm-rebuild token assertions; model/recipe cache separation |
| Lineage schema/recipe/rule/ontology/extraction-spec digests and receipt IDs | Processing configuration / execution references stored once and referenced by contributions/results | Whole graph lineage envelope, duplicated configuration per fact | Immutable input/recipe identity and dependency invalidation preserved |
| Artifact manifest `id, artifact_type, artifact_ref, artifact_hash, producer, depends_on, metadata` | Necessary content/index/product installation metadata with typed dependency references | Generic graph artifact manifest and JSON export used as runtime database | Installed bytes/digest and current contract verified before publication, not on every normal query by full scan |
| Aggregate `protocol, snapshot_version, id/snapshot_id, project_id, created_at` and every aggregate collection | Project scope and input/evidence identities remain on their actual native owners | `SemanticArtifact` aggregate persistence, snapshot ID/version chain, checkpoint, aggregate serialization and collection transport | Build/query/report/reader/restart paths operate without creating or accepting the deleted aggregate |
| `entity_mentions, extraction_spec, source_classifications, classification_profile, conflicts, metadata` aggregate fields not otherwise admitted above | References to their explicitly named native/configuration/product owner only | Catch-all collection retention, second schema owner, arbitrary aggregate metadata | Producer and every consumer aligned; stale `reports` canonical-record enum removed rather than reintroduced |

The whitelist does not authorize a second custom SQL fact store. Native RDF
facts are the primary Semantica knowledge, the carrier is document content,
indexes are disposable search access paths, and reports/organization are
product results. Neither a JSON graph nor a report context may duplicate those
owners. It also does not authorize retaining two complete parsed formats:
choosing the single carrier remains a parsing gate, with exact range and
structure fidelity required before deleting the redundant representation.

### Minimum cross-index visibility design, not yet proven

1. The existing native worker owner exclusively opens the Oxigraph store and
   owns writes/queries; callers must not each open the same RocksDB directory.
   The probes used sequential writer/reader processes. Concurrent-process
   opens, lock ownership, crash/reopen and packaged lifecycle are still gates.
2. Build required keyword/vector access paths in staging under exact immutable
   source/material/model/recipe identities. Use native index transactions and
   bounded batches; flush and validate before publication. No original body
   duplication or independent fact/evidence versions are admitted.
3. Publish one small active index binding and the corresponding native source
   contribution in a single Oxigraph atomic update only after all necessary
   access paths are durable. This is an activation reference, not a snapshot
   containing knowledge. There is no claimed ACID transaction across engines.
4. Each request captures that small binding once and uses the same binding for
   candidate retrieval, native record reads and provenance checks. The existing
   owner fences publication against in-flight reads, or rechecks the small
   binding before returning and emits a typed stale/retry result on change.
   The exact locking strategy requires an integration proof; several SPARQL
   calls do not by themselves constitute one native read transaction.
5. Removed/replaced inputs become explicitly stale or unavailable immediately.
   Native liveness/authorization restricts candidates **before** ranking in
   both indexes; global top-k followed by filtering remains forbidden. Shared
   facts retain other valid source support. An index unable to enforce that
   candidate scope must reject the query, not silently reduce recall.
6. On failure before activation, discard the incomplete installation and expose
   the required pending/failed/stale state. Do not serve an obsolete source as
   a hidden fallback. Keep only active and genuinely in-progress handles;
   retire abandoned/superseded indexes after checking in-flight references.
   This is not retention of historical knowledge generations for runtime reads.

Acceptance requires injected failures before/after every durable write and
activation, concurrent query/removal/replacement, crash/restart, cross-project
isolation and proof that no response combines contributions from different
bindings. These tests are not supplied by the RDF term roundtrip probes.

### Fidelity and resource evidence still missing

The existing seven probes passed in the earlier recorded run (7 passed in
25.94 seconds); they were not rerun for this documentation appendix. Their
positive evidence covers selected scalar terms, qualifications, two-source
withdrawal, sequential restart and point reads. It does not close the following:

- Scalar corner cases: finite-float policy, numeric precision beyond the
  fixture, structured objects, absent fields and all status transitions.
- Mention/identity merge/split, every classification cardinality and vocabulary
  parent, community/topic membership lifecycle, conflicts and user-edited
  report dependencies. None has a complete native-consumer fidelity fixture.
- Exact quote reconstruction from the selected carrier: multi-page ranges,
  OCR order/coordinates, repeated text, tables/merged cells and Unicode spans.
- Atomic source publication across indexes and native facts, pre-ranking
  permission/source filtering, actual host worker process ownership and native
  query cancellation. Sequential persistence is not concurrent integration.
- Native engine resource control: a 20,000-row fanout correctly rejects the
  result cap, but a 2 MiB scalar allocates 6,817,910 Python bytes before a
  1 KiB cap rejects it. Row/byte caps therefore do not bound single-term
  allocation or native execution. Large content must remain in the carrier;
  admitted scalar/text fields need producer bounds and bounded projections.
- A preset cancellation event does not interrupt Oxigraph execution. A
  separate synthetic expensive-query child was stopped by SIGTERM in
  4.183 ms after its 200 ms timeout and the durable store reopened. That proves
  a process-boundary option, not working product cancellation. Reuse existing
  worker lifecycle and verify cancellation, cleanup, lock release, restart and
  lossless queued-operation handling before acceptance.

G1 is in progress; these specific production owner/consumer and fidelity gates
remain unproven.
Passing capability tests, changing a storage class or deleting aggregate files
cannot substitute for them, and later packaging must not bypass this gate.

### Test-only native publication and bounded reference paging proof

Added `tests/test_native_publication_audit.py`; no production publication
implementation or second storage owner is introduced. Result:
`.venv/bin/python -m pytest -q tests/test_native_publication_audit.py`:
**10 passed in 4.24 seconds**. Synthetic temporary data only; no model, network
or formal profile access. The earlier seven capability probes were not rerun.

The publication fixture keeps exactly one mutable native fact in Oxigraph.
SQLite contains only input identity, record reference and derived search term,
never a fact/evidence/document body. A native atomic update marks the source
pending and removes its active index binding **before** the fact changes.
After index installation/validation, another conditional atomic update marks
the source ready and exposes its binding. No knowledge snapshots are created.

Observed cases:

- Interruption after invalidation, fact replacement or staged index install
  remains explicitly unreadable after an independent process reopens the store.
- An abrupt `os._exit(73)` after durable fact mutation also reopens as pending.
- Corrupt staged bytes and a valid old-input index cannot activate; a complete
  new installation reopens ready with exactly one current fact value.
- Deterministic interleavings invalidate a read when publication changes after
  its native read/index lookup, including a complete replacement that returns
  to ready. A parse-invalid compound native update leaves the previous state
  unchanged. No response combines old features and new facts in these cases.

A separate paging fixture has 23 native facts plus a foreign project reusing
the same 23 record IDs. Its SQLite access path contains only
`project, source, term, record_ref` with composite primary key and `WITHOUT
ROWID`. The native fact bodies remain only in Oxigraph. A source-scoped SQL
keyset query returns four pages of 6/6/6/5 references, followed by exact native
project+ID reads. A direct seek beyond record 17 reads only five native records.
SQLite `EXPLAIN QUERY PLAN` identifies `SEARCH features USING PRIMARY KEY`,
without a table scan or temporary ordering B-tree. Project/source filtering
precedes candidate selection; foreign values never appear. Cancellation
before page retrieval or between the page and first native point read performs
zero native reads. This cancellation check does not interrupt an already
running native call.

Limits remain explicit: this is one derived index plus the native fact owner,
not actual keyword+vector publication, product report/reader integration or a
production storage schema. Read-race hooks are deterministic single-owner
interleavings, not proof of a concurrent lock implementation. Files are assumed
immutable after validated installation; tamper-resistant query-time block
verification is not established. Digesting tiny fixture index files at install
time is not permission to hash a production index on every query. Temporary
old-index files exercise rejection and pytest removes the entire fixture;
production in-flight retirement/physical cleanup still needs its own proof.
The tested SQLite plan is evidence for this exact composite-key access path,
not all text/substring/vector retrieval or native RDF fanout enumeration.

### Additional native semantic-field fidelity capability probes

Added `tests/test_native_semantic_field_fidelity_audit.py`:
**5 passed in 1.72 seconds**. Each write/modify/verify phase runs in an
independent child process against temporary native Oxigraph data. There are no
model/network calls, real-profile reads or production schema changes. All
semantic fields use explicit RDF terms/predicates, never serialized JSON.

| Capability fixture | Verified after process restart | Boundary still requiring production evidence |
| --- | --- | --- |
| Mention/entity identity, aliases and chosen merge/split | Representation/item/start/end survive; explicit merge changes the mention target and adds one alias; explicit split restores the previous target and withdraws only the merge-produced alias | The fixture supplies the chosen merge/split, not an identity-resolution algorithm. Shared alias support, candidate bounds, real owner calls and transactional dependent updates remain untested |
| Conflict kind/reason/claim/evidence references and status | Typed reason text and referenced claims/evidence survive open → resolved → ignored → open changes | Which transitions are valid, permissions, conflict detection, resolution provenance and consumer rendering remain owner behavior, not RDF behavior |
| Classification cardinality, vocabulary parent, assignments, confidence/evidence and unclassified dimension | Single/multi configuration and parent edge survive; one sector and two themes remain distinct; decimal confidence and evidence retain identity | Native RDF admits a second assignment to a single-cardinality dimension. This is an explicit limitation: the native classification/publication owner must enforce cardinality and hierarchy validity before activation |
| Topic/community membership and source withdrawal | Source-scoped shared membership/support survives withdrawal of one source; source-only member and child-parent edge disappear; last withdrawal removes all supported membership | Native storage does not automatically invalidate the remaining topic title after last support. Production organization owner must enforce validity, regenerate or explicitly mark stale; graph/product consumers must not display unsupported results |
| Qualifier absence/presence, typed scalars and precision | Missing condition remains absent; present polarity/condition/time/unit/value survive separately; integer 9,007,199,254,740,993 and a long decimal retain numeric precision; false differs from string `false`; URL literal differs from URL IRI | Native XSD doubles accept INF and NaN. Required finite-value validation belongs at producer/publication ingress; the storage capability is not proof that current producers reject nonfinite values. Decimal lexical scale canonicalization is not guaranteed merely by numeric equivalence |

These probes close the **uninvestigated storage representability** part of the
listed fields. They do not close producer-to-native-owner-to-real-consumer
integration, application validation or the fidelity gate as a whole. The native
engine preserving a hand-authored relation is not proof that an existing
builder/report/query implementation emits or consumes it correctly. In
particular, no opaque JSON escape hatch or second knowledge layer is needed to
preserve these tested fields, but schema/cardinality/lifecycle validation cannot
be assumed to be enforced automatically by RDF storage.

### Native vector owner: current upstream delta and capability closure

Read-only comparison with merge-base
`0a2731c8223426efaa0dd9e9b345a8411ff3d4f0` finds **137 added / 0 removed lines**
in `vector_store/sqlite_vec_store.py`. Persistence, native vec0 embedding
storage, add/delete, exact ID `get`, generic search and read-only reopen are
upstream owners. The additions include `add_groups`, `search_chunks`,
`search_groups` and their cancellation/deadline helpers. Calling these additions
upstream-native algorithms would be inaccurate: they are fork extensions of an
existing native persistence owner, not another vector database.

Current storage/query responsibility:

| Owner/path | Current behavior and reusable part | Redundancy / limitation to remove or retain explicitly |
| --- | --- | --- |
| Upstream `SQLiteVecStore.add/get` | Embeddings persist in vec0; `get(ids)` issues batches of `WHERE id IN (...)` | Native metadata can carry arbitrary JSON but the proposed minimal integration stores no fact/body there. `get` accepts an arbitrarily large input list; caller limits are still necessary. Evidence hydration needs native fact/locator reads, not returning vectors unnecessarily |
| Generic `search(filter=...)` | JSON auxiliary metadata predicates accompany native KNN | Previously demonstrated post-KNN filtering can lose qualifying results. It is not the admission mechanism for product source/project scoping |
| Fork `search_chunks:449` | `id IN (SELECT vector_id FROM vector_chunks WHERE source_id IN (...))` participates in vec0 KNN before k; returned rows are ID, distance and source/range only | `vector_chunks` is an access-path locator, not duplicate source text. Source list/parameter limits still need a production contract; project binding lives in the installed index owner, not a project argument to this method |
| Fork `add_groups:430` | `vectors_groups` holds vector/group/position and `vectors_group_sources` holds group/source IDs | These tables contain references, not knowledge bodies. Keep only if current semantic result grouping needs them; do not add another copy of member facts/evidence |
| Fork `search_groups:481` | Scope admission precedes native KNN; a group with any source outside scope is excluded; duplicate vectors do not exhaust group result count | It repeatedly asks for 256-vector frontiers with disk `knn_seen`, retains only top-k groups in Python and resolves ties. A large tie or sparse matching groups can require traversing all eligible vectors. Disk scratch is not proof of bounded total native work |
| `explorer/search_index.py:481/488` | Current semantic paths call `search_chunks` / `search_groups`, then resolve matched record references | They reopen a read-only store for each call. Group hydration still prepares a sparse snapshot-shaped object; migration should replace that consumer contract with direct bounded native fact/evidence reads, without inventing another aggregate |
| `explorer/search_index.py:1026` publication | Batches vector writes (128) and builds reference links on disk | Still accepts full snapshot collections to seed evidence/name/source lookup projections and uses previous/current record mapping. The aggregate input dependency must be removed in the agreed native-owner migration; staged reference joins themselves are not a second knowledge authority |

The earlier audit's full-matrix `rank_evidence` description is **not current
for the inspected product path**: `semantic_query.py:102/125` now delegates to
the persisted index methods above. No `rank_evidence` implementation remains in
`context/snapshot_search.py`. That file still defines candidate/projection
helpers and snapshot-shaped preparation, so absence of matrix ranking does
not mean the aggregate contract has already disappeared. Unrelated generic
ContextRetriever paths were not treated as evidence of the product call chain.

Existing `tests/vector_store/test_sqlite_vec_store.py:27` already covers group
recall across 300 duplicate foreign vectors and read-only reopen; `:42` checks
sparse-link SQL instruction work for a specific fixture; `:79` checks SQLite
progress-handler cancellation and scratch cleanup. Those tests were inspected,
not rerun or relabelled as product acceptance in this audit.

Added independent no-model, two-process evidence in
`tests/test_native_vector_owner_audit.py`: **2 passed in 1.56 seconds**.

- Chunk fixture: 301 closer foreign vectors and three own-source vectors.
  Fresh reader process with `top_k=2, source_ids=['own']` returns the two own
  hits, not zero hits from post-filtering foreign top-k. Empty/missing scopes
  return none. Native `get` reads exactly those two IDs with empty metadata;
  SQL trace shows scoped KNN and `WHERE id IN` hydration, no whole-vector fetch.
- Group fixture: 300 foreign vectors, two own groups and one multi-source group.
  Own-only scope returns both own groups; expanding scope admits all four
  groups. Links contain only the declared ID/position columns; temporary
  `knn_*` scratch is absent after completion. Both publication and read phases
  use distinct processes and the same persistent native vector database.

This closes G1's basic capability question: an existing persistent native
vector owner can restrict source candidates before ranking, reopen across
processes and fetch explicit hit IDs without a Python full-vector matrix or
second fact store. G5 product integration/performance is a later gate, not a
prerequisite to acknowledging this capability. Conversely, the probes do not
prove an ANN index, bounded engine read bytes, large-scale exact/grouped KNN
latency, project installation integrity, real embedding-space invalidation or
keyword/vector/native-fact joint publication. sqlite-vec exact KNN can scan
eligible vectors internally; a small returned result count cannot establish
constant-time retrieval. Those remain explicit implementation/acceptance work.

### Joint native-fact, keyword and vector publication capability probe

Extended `tests/test_native_publication_audit.py` with two subprocess-based
joint-publication probes. The file now passes **12 tests in 9.99 seconds**.
All data is a tiny temporary fixture; there are no model/network calls or
production profile mutations. These probes replace the earlier "one derived
index only" capability limitation with actual native Oxigraph facts plus a
keyword feature/reference SQLite index and the existing `SQLiteVecStore`
native vector owner. Neither index contains fact, evidence or document bodies.

The exact dependency tuple is `(project, source, material, representation,
recipe, schema, facts_epoch, embedding_model, embedding_revision, dimension,
metric, keyword_recipe, vector_recipe)`. Both installed indexes must match
the native owner's entire tuple. A separate action changes each of these 13
vector binding fields individually and proves every mismatch is rejected.
An absent required vector file yields `missing_index`; a valid keyword index
does not turn that into partial success. One native activation update installs
both names/digests and switches publication to `ready`.

Every mutation/read phase reopens in another process. Before authoritative
mutation, a mismatched staged vector index fails admission while the existing
valid reference remains readable. After invalidation and native fact mutation,
`pending` and then `failed` block both previous and proposed references, including
after restart. A subsequent valid joint publication restores the new reference
and makes the old one explicitly `stale_reference`. Withdrawal exposes
`withdrawn`, removes the fixture source fact and blocks both retrieval modes.
This does **not** promise that failed updates can serve previous facts after
those facts have been changed; no historical graph is retained to fabricate it.

The target field contract is frozen separately in
[`2026-11-04-native-rdf-field-contract.md`](2026-11-04-native-rdf-field-contract.md).
It names RDF predicates, scalar types, cardinality/optionality and write/read
owners; preserves ordered typed attributes and actual string qualifier
semantics; and keeps the evidence set distinct from admitted support with
source/material lineage. There is no JSON literal or generic property-bag
escape hatch. Existing arbitrary `Dict`/metadata shapes are not silently
declared supported: a consumed field without a demonstrated typed mapping
remains an explicit G2 integration blocker.

This closes the minimal **joint-publication storage capability** question,
not G4 production implementation or product acceptance. The joint probe
hashes installed tiny files when activating; it does not compare them against
a pre-recorded staging digest or prove tamper-resistant query-time block
verification. Earlier single-index corruption tests remain narrower evidence,
not proof of that complete joint trust chain. Production admission, concurrent
writer/read locking, resource budgets, index retirement/physical cleanup,
real producer-to-consumer mapping and real ESG acceptance remain later work.
