# Canonical topology references for downstream organization

### Final checkpoint and artifact evidence (2026-11-03)

The final combined checkpoint, offline upgrade, reading-report admission,
project-stage, semantic-artifact and kernel-owner suites passed 193 tests in
242.08 seconds, including required typed-attribute admission. This supersedes
the intermediate 192-test result and pending qualification below.
The frozen development source digest was
`dbdcd6d418860e45bad83ce71653b31da69cff77deae7fd9b3be7a80ce3b1bbb`;
the complete inventoried darwin-arm64 CPU artifact is
`sha256:f7bcd519c5660442616785e93699e7c2abbdedf8d2020a40b2a14ac2044e2b38`.
Relocated acceptance passed in 273,512 ms and subsequent cache receipt/inventory
verification passed. These identities refer to the frozen build input, before
this evidence-only appendix; appending this record does not relabel that input.

Actual native publisher → host adoption → UA child → provenance integration
passed all four tests against that artifact in 26.51 seconds. An earlier run of
the same integration hit its 30-second Python execution deadline; the unchanged
rerun passed. This intermittent failure is retained as evidence, not reclassified
as a deterministic product or provider failure.

No production pin or release is qualified by these development results. Real
semantic/model quality and cost remain unverified. Unchanged extraction and term
reuse still do not eliminate full immutable snapshot/topology publication or
vector-link rebuilding; delta-only write cost remains unimplemented.

### Offline extraction contract admission (2026-11-03)

Native owner `project_checkpoint_upgrade.recover_extractions` reconstructed old
hashes but installed them without the current extraction contract key. Runtime
then missed completed work and attempted paid generation. Reuse the existing
offline converter and native grounded relation parser: verify entity mention
identity and exact spans, relation endpoint/evidence/qualifier grounding and the
recorded extraction specification before installing the current key. Unknown
or incompatible results are rejected without changing the original dataset;
no runtime old-key lookup or model fallback is added. Original payloads and
receipts remain intact. The restart fixture now carries actual grounded IDs and
polarity; an ungrounded historical entity has a separate rejection regression.
The pre-fix restart cases failed on a forbidden model call. The combined native
suites passed 192 cases. A subsequent red specification also caught acceptance
of correctly located entities missing required typed attributes; conversion now
uses the existing native ExtractionSchema.validate_attributes owner. The final
combined suites and a newly built artifact are qualified separately.
Upstream assessment: this belongs to the existing offline checkpoint converter,
not the extraction runtime or a second cache implementation.

### Source-set identity in vector-only recovery (2026-11-03)

The native builder's completed-generation fence admitted a removed-source rebuild
as vector-only: every remaining source was unchanged, but the project was not.
The existing fence now also compares exact source/revision sets with the adopted
snapshot representations. This permits organization regeneration on source removal
while retaining the no-new-generation boundary for actual vector-only rebuilds.
The existing checkpoint parameterized regression reproduced two failures and now
passes all 16 cases, including removal, addition, revisions and model switches
(122.90s). No runtime fallback, alternate producer or dependency is added.
The wider checkpoint run still has two historical extraction-conversion cache
misses; this source-set correction does not claim to resolve them. A fresh native
artifact is required after this source change; an earlier in-flight snapshot is
not qualified as this implementation. Upstream assessment: repairs the existing
builder recovery predicate, preserving the native checkpoint owner.

### Native grounded topic production (2026-11-03)

Topology communities are no longer copied into KnowledgeTopic. The project
organization stage reuses the existing native `_explanation_reports` Overview
owner and its evidence-qualified findings, bounded prompt packing and receipts.
Each cited finding becomes a topic with the cited entities/assertions and
`metadata.organization` identifying its report and input digest. Uncited knowledge
remains canonical and accessible; it is not assigned an invented theme. The
deterministic recipe emits topology communities without pretending to have
model-qualified topics. No PDF is reread by this organization step. Recovery
persists its topics and receipts in the existing stage checkpoint.

Removed the manual project processing version constant; the native processing
identity now derives from current Python producer bytes, independently of
checkout location. No additional version-dispatch or old-topic fallback.
Consumers must preserve organization metadata and must not infer theme identity
from equal community memberships. UA organizes qualified themes, explicit index
navigation and reading scenes; the host does not perform semantic clustering.

Source evidence: reading-report admission, project stages, semantic artifact and
kernel-owner suites: 121 passed (8.60s). Wider checkpoint and rebuilt immutable
artifact qualification remain required. These use fixtures, not real model
quality or cost evidence. Shared cited passages can support several facts, so
cited membership is not proof of precise per-claim topic classification. Real
subject coherence and coverage remain a separate acceptance gate. Upstream
assessment: reuse the existing native CommunitySummarizer rather than introduce
a host topic engine; reconcile this projection with upstream native topic
production if equivalent capability becomes available.

### Candidate projection RSS correction (2026-11-03)

The next real offline adoption reached the unchanged 512 MiB RSS stop threshold.
`context.snapshot_search.iter_snapshot_candidates` still retained all evidence
quotes and entity records, although the authenticated reader streamed them.
The native candidate owner now stores only ID-to-representation/name lookups in
an ephemeral SQLite database, with a 2 MiB page cache, and reiterates records.
Candidate order, text, grounding and keyword semantics remain unchanged. Both
reference and vector publication callers place temporary lookups inside their
staging directory; no second algorithm, persistent fact store or fallback added.

Red regression: 6,000 generated 8 KiB quotes allocated 51,164,724 traced bytes
before the first candidate, violating an 8 MiB bound. The same regression and
native snapshot/document keyword suite now pass: 81 tests in 9.89 seconds.
Complete artifact qualification and real migration within the existing resource
budgets remain pending; source tests alone do not close either requirement.
Upstream assessment: fixes the existing native projection owner and its two
publisher callers; no new dependency or alternate retrieval path.

### Retrieval manifest streaming correction (2026-11-03)

The previous bounded offline reader passed 79 source tests and complete relocated
artifact acceptance, but failed the authorized real adoption at
`retrieval_manifests[0]`: a retrieval inventory can exceed the 4 MiB knowledge
record limit through its membership arrays. No replacement index was published.
The native `_staged_authenticated_snapshot` now stages those member arrays one
bounded item at a time; the same `_write_reference_index` publisher streams them
through the standard JSON encoder. It still derives the exact original graph
digest and offsets; no limit increase, source rewrite, host parser or old-format
reader is introduced. Individual oversized values remain rejected.

Regression: a manifest with 100,000 member references fails before the fix and
passes afterward, checking authenticated offsets after the manifest as well as
unchanged canonical identity. Native snapshot/document keyword tests: 80 passed
in 6.83 seconds. Complete artifact rebuild and real-adoption resource acceptance
remain separate required checks. Upstream assessment: this corrects the existing
offline reader/publisher seam; no alternative publication implementation added.

### Authenticated streaming offline reindex (2026-11-03)

The fixed adopted project's old index is actually `keyword-references.v1` and
contains only metadata/records/terms/postings. The address-upgrade owner correctly
rejects it; changing its format label would falsely qualify absent current search
tables. Retain that rejection. Reuse `GraphSearchIndex.index_artifact` and the
single current `_write_reference_index` publisher instead: require exact canonical
digest/project/snapshot, stream bounded JSON values into an ephemeral disk staging
table, then publish all current references/search tables using the native producer.
The temporary snapshot is deleted on success or failure; no runtime old-index
reader, fallback, semantic inference or persistent second knowledge store is added.
This owner indexes an already authenticated adoption, not untrusted new knowledge.
Admission and streaming share one graph read; the publisher independently derives
the same canonical encoding digest and checks unchanged file identity before output
publication. One maintenance value is at most 4 MiB; host normalized reads remain
64 KiB. Source-artifact indexing still uses its existing bounded-document owner.

Affected callers: offline native/document-query regressions and the explicitly
authorized fixed-project maintenance command in OntoScience. The red regression
failed at the old whole-file `read_bytes`; source and complete relocated artifact
qualification are pending for this correction. No release pin is changed.
Upstream assessment: no equivalent bounded offline canonical reader was found in
the inspected native search publisher; consolidate here if upstream supplies one.

- Date: 2026-11-03
- Status: implemented; source regressions verified, complete artifact qualification pending
- Inspected base: 24ef31681 (working tree contains independent search changes)
- Upstream reference: not reviewed

## Native capability assessment

Reuse `GraphSearchIndex._write_reference_index` and the canonical artifact schema.
The normal incremental builder already calls this publisher. Its `records` table
authenticates exact canonical byte ranges; downstream organization additionally
needs indexed endpoints, memberships and evidence references. These are absent
from the existing index, causing OntoScience to reconstruct facts and evidence.
No extraction, identity, clustering, ranking or conflict algorithm is added.

## Approach and deletion boundary

Index canonical endpoint/membership/evidence identities alongside existing record
references, including assertions with literal objects (nullable target). Add
communities and source relations to the same record-reference owner. Bodies,
qualifiers, quotes and immutable representation identities stay in canonical JSON.
OntoScience must remove its duplicate fact/evidence production and consume these
references; UA remains the organization owner. No new version ladder or fallback.
This changes index capabilities and requires rebuilding/qualifying the exact native
artifact and updating all consumers; source-only success is not release acceptance.
No model/network/PDF access is required by the new regression.

## Verification and upstream merge assessment

Pending regression execution and artifact qualification. Upstream disposition:
pending; retain only while the native reference publisher needs these indices.

### 2026-11-03 implementation and verification correction

The planned record above is historical. The current publisher now writes
`semantic_links`, `semantic_members` and `semantic_evidence`, with indexed graph
addresses for literal assertions and original canonical bodies preserved by byte
reference. Incident relation queries have `(source_key,id)` and `(target_key,id)`
indexes: the red regression demonstrated a temporary sort despite LIMIT; the
fixed EXPLAIN plans search the index without that sort.

Incremental production extends this same publisher, not a second index owner.
`SnapshotRef` now requires the baseline index path/digest as well as the graph
identity. The host must obtain both from the authenticated artifact manifest.
The publisher verifies baseline digest, project, snapshot, graph and current
capabilities before writing outputs. Unchanged candidate postings are reused
only under their actual input digest (including endpoint names and evidence
sources); unchanged document positions/ranges/locations are reused under parsed
artifact, representation, text and location identity. Withdrawn records/terms do
not enter the fresh publication. Canonical JSON and topology references are still
written for each immutable publication, and vector group links are rebuilt from
current evidence; this is not a claim of delta-only I/O or bounded update cost.
The source extraction/checkpoint owner remains unchanged.

Affected consumers: semantic artifact builder, SnapshotRef schema, downstream
host request/checkpoint identity and manifest admission. Existing indexes lacking
the required input identity are rejected for incremental reuse; rebuild explicitly,
never infer a sibling file or fall back to an older producer. The output remains
the one current reference-index contract; no alternate reader/version dispatch.

Source evidence: topology/query/artifact/contract regressions 111 passed in
13.98s before final checkpoint consumer updates; incremental red test failed on
the absent publisher argument, then passed with unchanged-document tokenization
forbidden. Further checkpoint and full relocated native artifact qualification
must be recorded separately. No PDFs or paid models accessed by these tests.
The OntoScience release pin has not been updated or qualified by this source run.
Upstream merge assessment remains pending; reconcile with upstream native
publisher and remove this fork delta if it offers equivalent authenticated
topology/input reuse. Concurrent independent search changes are preserved.

### Bounded presentation fields (2026-11-03, implemented)

The fixed real snapshot has a 1,347,520-byte topic and 145,068-byte entity;
the host's 64 KiB whole-record reader therefore cannot organize this corpus.
Reuse the same `_write_reference_index` owner to authenticate field byte ranges,
without storing another copy of labels or facts. Host organization reads only
its bounded presentation fields; membership/evidence arrays stay native indexed
references. No version dispatch, new parser, truncation or larger read budget.
Callers: native publisher/offline publisher, host reference reader/organization
worker and their native wire fixtures. A red regression reproduced missing field
addresses; the native snapshot suite passed 58 tests after implementation.
Coverage includes Unicode byte offsets, nested metadata and escaped JSON Pointers.
The existing fixed snapshot still needs an explicitly bounded
offline reindex; this does not claim that migration or release qualification.

### 2026-11-03 bounded offline address maintenance

Inspected `GraphSearchIndex.index_artifact`, `_write_reference_index` and
`ReferenceGraphSearchIndex._read_record` at the same fork HEAD. The offline
publisher parses a complete SemanticArtifact; the reader deliberately limits
query reads. Neither is a bounded maintenance operation for an existing 309 MB
artifact. Added explicit `upgrade_reference_index`: authenticate the existing
native reference index, preserve its terms/positions/vector tables, traverse
canonical record addresses in offset order and build missing topology/field
addresses with the *same* native schema and record writer as normal publication.
Whole-graph authentication shares this single pass. No graph rewrite, model,
PDF read, host fact copy, runtime fallback or new format version. Per-record
maintenance input is capped at 4 MiB; consumer presentation remains 64 KiB.
Old indexes without content-bound incremental inputs do not gain that metadata.

Regression first failed with the missing native method; the native snapshot
suite now passes 59 tests, including unchanged search results and rejected index
digest corruption, with whole-file read_bytes forbidden during upgrade.
Actual fixed-snapshot migration and the rebuilt native artifact remain pending.
The general `index_artifact` full-object path is unchanged and is not qualified
for large offline migrations. Upstream assessment: maintenance extends the
native reference publisher, so merges must retain the shared writer rather than
introduce a second index implementation.

Follow-up: authenticate the reference index while copying it to private staging,
instead of hashing it and then reading it again through SQLite backup. Canonical
input bytes are read once per file; later SQLite reads touch the staged output.
Reject aliased input/output paths. Added interrupted/identity/whole-graph-gap
corruption publication checks and exercise upgrade with a >1 MiB membership
record; qualification results will be recorded after execution. Existing source
and the immutable canonical graph are never modified by maintenance.

Verification: `tests/test_native_snapshot_search.py` passes 62 tests (3.49 s),
including the added interruption, whole-graph corruption and >1 MiB membership
upgrade checks. The native artifact must be rebuilt for the single-pass change;
the prior build does not qualify that source revision.

### 2026-11-03 organization fact partition cost

Inspected the current native `_semantic_organization` caller in `_project_stage`
and `CommunityDetector.detect_communities` at HEAD
`24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`. Each detected community rescanned
all assertions and canonical relationships, multiplying fact visits by community
count. Reuse the existing detector and membership semantics; partition facts by
its entity assignment once, preserving input order, literal assertions and
internal-edge identity. No model call, new algorithm, cache version or host owner.

Regression `test_organization_partitions_facts_without_rescanning_per_community`
first failed with 297 assertion visits for 3 assertions and 99 communities.
Green regression and the affected kernel-owner suite pass: 40 tests in 7.23 seconds
(`.tmp/deep-native-organization-rescan-green.log` in the consumer workspace). This removes
redundant traversal, not the semantic Overview defect or whole-build I/O.
The prior dev artifact does not include this source change. Upstream assessment:
retain only if the upstream organization owner still rescans per community;
otherwise drop this optimization in favor of that owner.
