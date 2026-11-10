# Completed results and source identity

- Record ID: 2026-11-10-completed-results-and-source-identity
- Date / author: 2026-11-10 / OntoScience maintainers
- Status: implemented-unverified (focused specifications pass; product acceptance pending)
- Fork base revision: bb418942ed6ca8f6c54ec9773ba312070386564c
- Upstream reference: not refreshed during this change
- Related records: OntoScience `code-identity-coupling-audit-2026-11-07.md`; commits pending

## Reason and scope

Transport-bound source hashes changed on relocation or rename. Projection misses
then reconstructed observations whose accepted native projections already existed.
Generation replacement and ordinary result reads must not repeat completed work.
The historical production error is `Native fact projection differs from existing
derivation`; a read-only sample compared 418 projections without differences, so
its particular field-level cause is not established by this change.

## Native capability assessment

- Existing owners: `ExtractionRecords.source_projection`, immutable extraction
  operation bindings, `PublicationRecords`, `QualifiedFactIndex`,
  `IdentityCandidateIndex`, `SQLiteVecStore`.
- Callers inspected: `semantic_publication_builder`, `semantic_source_artifact`,
  `native_maintenance`; native lifecycle, handoff, projection and publication tests.
- Decision: repair existing owners. ConflictDetector remains the semantic reducer;
  no alternate resolver, cache database, snapshot engine or fallback reader added.

## Approach and actual changes

- Source identity explicitly selects project/source/material/accepted parse and
  semantic extraction inputs. Absolute path, display name and executable digest
  are excluded. The completed header retains the immutable accepted operation
  collection; normal lookup does not derive that collection by scanning facts.
- Completed publication lookup precedes source restoration; a failed newer task
  does not hide an active completed publication. Replacement preserves valid
  identity/fact decisions. Embedding changes reuse knowledge stages.
- Existing observation addresses are consumed directly. Removed occurrence
  ordinal reconstruction and repeated fact/identity projection production.
- Canonical consumers read committed decisions without reducer callbacks.
  Native endpoint/coverage/qualifier checks still reject malformed stored data.
- Offline `rebind_source_projection` verifies bindings and addresses before
  changing lookup subjects. Published IDs and accepted observations are unchanged;
  normal reads do not probe historical keys. Host migration handles parsed-source
  selectors separately, without rewriting their immutable carriers.
- Model/network impact: no new model or service; successful reuse makes no paid
  calls. Existing receipts and vector identities remain owned by their stores.

## Verification and limitations

- Focused native regressions: 124 and 185 tests passed in earlier affected runs;
  100 publication/fact/maintenance tests passed; malformed count/activation scale
  4 passed; corrupt-policy rejection passed.
- `tests/test_native_projection_lifecycle.py`: relocation/rename prohibit body
  reads and source rebuilding; embedding-only regression passes and permits only
  embedding calls, forbidding classification preparation, identity and fact
  reduction.
- Persistent 56,700-observation / 21,620-group activation: 2.614 seconds.
- Latest timed scale run: native read 14.641 s; semantic reduction 5.144 s;
  completion commit 0.224 s; total read/sort/reduce/commit 43.705 s; completed
  lookup 0.000664 s. Maximum RSS 768,999,424 bytes. Package acceptance ran
  concurrently. An earlier 26.15 s result is not a stable p95 or a first-build
  performance pass. Evidence: host `.tmp/identity-fact-scale-timing.log`.
- Full packaged ESG ready/report/evidence acceptance, idle cold/hot repetitions,
  original mismatch reproduction and full dependency-invalidation acceptance are
  not yet complete. Focused tests are not release acceptance.

## Upstream merge assessment

- Disposition: keep repair of existing fork owners; review on each upstream merge.
- Incoming upstream revision: not reviewed in this change.
- Likely overlaps: publication builder, extraction records, vector store.
- Adapt/remove only when the current upstream owner supplies these same identity,
  reuse, evidence and integrity guarantees; do not preserve a parallel engine.
- Required checks: native projection lifecycle, handoff, maintenance, publication
  integrity, scale and host Library acceptance against the exact packaged source.

## Dated follow-ups

- Packaged ESG run `b6131e14-edfe-4166-92c2-483a3abbfbd1` reached source 6/38
  then failed with `Native source projection address budget exceeded`. The
  inspected owner at `8e92ce34`, `ExtractionRecords.source_projection`, incorrectly
  capped a streamed document at 16 MiB / 100,000 addresses. The existing owner now
  bounds each address and retained write batch, not the complete traversal.
  Selected evidence reads retain their cumulative response budget. Completion
  still follows durable writes, cancellation leaves no completion, and oversized
  individual addresses remain rejected. No alternate store or reader was added.
  The new >16 MiB streaming regression failed before this repair; it verifies
  bounded batch rows/bytes, one-address point lookup and complete traversal.
  Extraction/projection lifecycle specifications passed (29 tests); packaged
  continuation and first-build performance remain pending. Upstream merge review
  must preserve these bounds in this fork-owned source projection owner.

- Packaged ESG run `2d60dabb-c0a1-4944-8c4f-e797589a4237` exposed an omitted
  migration: the interrupted publication was stored in the flat registry graph,
  with no generation/latest pointer. New-generation CAS therefore matched no row.
  `PublicationRecords.migrate_pending_registry()` now validates completed identity
  membership/count/coverage before admitting the existing identity graph by
  reference and creating a pending publication header. No graph is copied or
  moved. Incomplete facts receive no completion binding. This explicit offline
  operation is idempotent; normal begin rejects unmigrated data and does not
  dispatch to an old reader. Ready flat publications require separate audited
  admission and are explicitly rejected by this pending-only migration.
  The first real migration used the superseded `MOVE GRAPH` implementation and
  took 672.0 seconds; that timing is not evidence for reference-only admission.

- 2026-11-10: New native bundle acceptance passed. Host App packaging and isolated
  change-verification are running; delivery is not yet certified.
- Final focused owner run: 133 passed in 101.21 seconds (projection lifecycle,
  maintenance, source traversal, publication, qualified facts and vector handoff).
  Source-removal specifications verify affected membership replacement and
  immutable preservation of prior decisions; unchanged partitions skip reduction.

- Packaged ESG run `7353a3fe-a64a-4efb-9fdc-7b96af1098b7` was canceled after
  completing 45,580 mentions and 25,286 canonical entities: native sampling found
  the worker inside Oxigraph Cartesian-product evaluation during identity sealing.
  An isolated persistent-store reproduction of the correlated coverage query took
  54.551 seconds for only 1,000 members. `PublicationRecords.seal_identity_stage`
  now subtracts the projected registered-decision member set once with SPARQL
  MINUS, rather than reevaluating all canonical/graph combinations per mention.
  Exact coverage semantics and missing member/selector/count rejection remain;
  an unregistered canonical cannot satisfy coverage. The new structural red spec
  failed on the preceding implementation. The replacement coverage query took
  0.270 seconds for 45,580 members; complete owner sealing took 2.836 and 4.431
  seconds in two persistent synthetic runs. The scale regression requires <5 s.
  These measurements do not certify full first-build performance, report output,
  or a zero-work second packaged build; requalification is required.

- 2026-11-10 regression correction (inspected `aaab34054728`):
  `76c81d2e` had explicitly forbidden correlated coverage queries.
  `bd6a25f3` (2026-11-10 05:45:56 +08:00) introduced immutable decision graph
  references, replaced that coverage lookup with correlated `FILTER NOT EXISTS`,
  and removed the corresponding test assertion in the same change. A query-count
  assertion on three members did not constrain query execution work. This repair
  keeps immutable graph references and replaces only the defective coverage plan.
  The restored structural guard fails before executing the known Cartesian plan;
  persistent 45,580-member tests also enforce the existing <5-second full-seal
  budget for both one and eight decision graphs. Equal-count member replacement
  and unregistered decisions must fail exact coverage without publishing a
  completion marker. These specifications run in the existing main/PR CI suite.

  `IdentityCandidateIndex.build` also omitted the current stage's explicit rule
  policy when reusing previous features. The next generation consequently lost
  reuse eligibility. It now persists that policy for reused features too.
  Multi-generation specifications forbid raw-row restoration, compare prior
  completed graph contents, and require a changed policy to restore raw rows.
  The obsolete same-stage rebuild fixture now creates a new generation; the
  existing prohibition on mutating completed stages remains. Returning to an
  already completed input must reuse the entire stage, without indexing or
  hydrating components. No alternate owner or compatibility path was added.

  Red verification temporarily restored both defective methods in memory only:
  all three selected cases failed (missing rule policy and both coverage guard
  variants). No production data was changed. Focused green results and packaged
  delivery are recorded below after verification completes. Library acceptance
  remains `capability-library-prepare`, primary owner `journey-library`, delta
  `keep`; these owner specifications do not replace product acceptance.

- Final regression verification for this correction: 100 owner specifications
  passed in 206.97 seconds; both fact-query structural cases passed separately
  after their final guard edit. A serial persistent-scale receipt passed all
  three cases in 39.31 seconds (including fixture construction): identity sealing
  for 45,580 members took 3.019 seconds in one decision graph and 4.949 seconds
  in eight; activation for 56,700 relations / 21,620 facts took 1.999 seconds.
  The <5-second identity and <=5-second activation budgets were not relaxed.
  The eight-graph result has little budget headroom; these are local runs, not
  p95 certification. Earlier full-run activation failures above five seconds
  motivated the additional access-plan correction; isolated success was not
  treated as sufficient evidence.

  Activation now subtracts the projected admissible relation set and groups
  membership by relation to reject duplicate fact ownership, avoiding correlated
  membership checks and a member-table self-join. Missing member/selector counts
  retain their separate exact check, scoped to registered decision graphs with
  MINUS; malformed, fractional and negative counts still fail. A trial combining
  that check via OPTIONAL caused an optimizer stall and was discarded. The final
  specifications also reject equal-count foreign replacement and cross-fact
  duplicate membership, leaving the publication pending.

  Evidence: /tmp/semantica-protection-final.log and
  /tmp/semantica-protection-scale-receipt.log (local ignored test evidence).
  No user data, extraction receipts or completed decisions were rewritten.
  App repackaging, real ESG rerun and host change-verification were not performed
  for this focused correction; the installed App still requires a new artifact.

### 2026-11-10 entity preparation regression: interrupted stages and many small operations

Inspected revision `ca6c59f3fda119b65acbb53cd9e3b15657c1a034`.
The existing owners are `PublicationRecords.build_page`,
`IdentityCandidateIndex.build`, and the builder's `native_rows` caller.
No upstream resolver replacement is involved.

The production-shaped trace had 14,823 operations and 45,580 entity mentions.
The first 12 pages (1,536 mentions) spent 5.266 of 7.60 seconds sorting the
same operation set 12 times, and 2.05 seconds querying 645 individual operations.
The repeated paging dates to `2cf2e28f`; feature reuse in `76c81d2e` incorrectly
required the whole previous decision stage to be complete. `bd6a25f3` retained
that condition. Thus cancellation repeated raw preparation. The previous
64-source fixture with one dense operation per source did not expose this
many-small-operations access pattern. Historical 39 ms completion reuse was not
a first-preparation timing.

Repairs in the existing owners:

- A build-scoped iterator retains only its next address, sorts operations once,
  and queries bounded 128-operation windows. Cursor restart, scope isolation,
  cancellation and byte limits remain. Address-only consumers pass `fields=[]`;
  they do not restore a name dictionary that is immediately discarded.
- Compact identity features are checkpointed in their existing RDF owner,
  independently of whole-stage completion. Same-policy immutable native
  references reuse features after same-attempt and cross-generation restart.
  Empty attempts do not hide earlier feature stages. Removed the temporary-file
  feature carrier; native raw input is consumed once, context preparation uses
  compact features, and progress distinguishes preparation from indexing.
- Detaching a shared stage no longer deletes its global completion binding.
- An explicit offline completion rebind audits rule policy, exact native mention
  sets, complete decision plans, exact decision coverage, unique ownership and
  sealed counts before adding a registry reference. It copies no result data.
  Normal lookups never search old keys or perform this audit.
- Decision-plan count casts run after per-decision aggregation rather than per
  support row. Member and selector joins remain separate; malformed, missing,
  negative and duplicate counts still fail.

Verification: 148 affected owner/pipeline tests passed in 97.43 seconds;
6 offline migration corruption cases passed separately after adding index-count
and duplicate-member cases. The 45,580-member seal took 2.048 seconds in one
and 3.579 seconds in eight decision graphs in the focused scale run. The existing
5-second budget is unchanged. Read-only traversal of all 45,580 real native
addresses took 9.765 seconds, 121 SPARQL calls, one operation sort and 4,297 quad
seeks (RSS 231.73 MiB), versus the previous field-restoring path's 56.737 seconds
and 457,495 quad seeks. This traversal is necessary only on a completion miss;
it is not a completed-result lookup benchmark.

Acceptance: `capability-library-prepare`, primary owner `journey-library`, Case
delta keep. Full packaged ESG ready and unchanged-input verification remain
pending at this source commit. Real-data offline rebind is not claimed here.
No schema, semantic rule or upstream merge changed in this correction. Keep this
owner repair on upstream merge only while upstream lacks these publication
contracts; do not preserve it as an alternate engine.

### 2026-11-10 packaged ESG follow-through: physical fact reader

Packaged revision `c9d8357e` confirmed source projection 38/38 reused,
classification 110 ms and entity completion 68 ms, with zero entity preparation,
indexing and comparisons. The next, distinct blocker was
`QualifiedFactIndex._physical_rows`: the worker sampled inside Oxigraph nested
loop joins before the first fact partition. This is fork publication-query logic,
not the upstream semantic reducer. The query joined the current publication's
operation set and dynamically addressed source/target identity graphs for every
canonical subject. The two-subject scale fixture did not represent 25,286 real
canonical entities and 14,823 operations.

The existing reader now follows indexed canonical-member and native-source
adjacency, filters operations against the current publication, and reads only
required fact/projection fields. Endpoint membership is checked against the
current head and exact decision-graph pointer; ambiguous membership, missing or
duplicate fields, evidence ordering, qualifier schema and subject byte/row limits
still reject. A bounded 128-entry endpoint memo lasts only for this traversal;
no new persisted index, temporary observation carrier, engine or fallback exists.
Completed fact lookups still return before this traversal.

Regression protection forbids cross-graph SPARQL in the physical reader and
measures indexed seeks with 64 separate source operations and 128 separate
identity decision graphs, as well as existing corruption and semantic-oracle
cases. A dynamic-graph SPARQL rewrite was measured and rejected; it retained
query-plan amplification. Direct indexed reads completed the real read-only
28,350-observation traversal in 59.266 s / 232.16 MiB. This is not a performance
pass: read-only RocksDB sampling showed repeated random index/string reads.
On the persistent 56,700-observation / 21,620-group fixture the full first build
was 28.998 s: native read 14.892 s, semantic reduction 1.842 s, completion commit
0.137 s, completed lookup 0.008 s. The completion budget remains 5 s. Neither
that fixture nor the read-only trace proves packaged end-to-end acceptance;
updated packaged ESG and unchanged-input verification are pending below.

### 2026-11-10 physical support identity correction

Packaged `d744ba75` ESG run `e7235dee-1acf-45ad-8eb3-9ec2b95b86d6`
reused entity completion in 35 ms but rejected fact processing after 6.53 s.
Read-only inspection proved operation `db4cfadede056afaea2cdbdf8ea69285f5c8dd8010e99c3ba81543dd8199b5cf`
relations 0 and 3 are different native supports of the same public projection.
Commit `4f2b87548` introduced a uniqueness check on public assertion/relation
IDs, contrary to `_build_source`'s existing proposition identity. Its test
incorrectly required that rejection. This is our fork ownership error, not an
upstream reducer failure or corrupt paid data. The dynamic-graph reader added
in `bd6a25f32` was a separate query amplification already replaced above.

Repair is in `QualifiedFactIndex._reduce_partition` only: reject duplicate
native references; admit every physical support once; retain the reducer's
exact normalized representative ordering when several supports share one
public ID. Public IDs, canonical IDs and evidence references are unchanged.
No data rewrite, alternate engine, observation copy or temporary file is added.
The former public-ID rejection specification is replaced by shared-public-ID
coverage/evidence tests in both traversal orders and duplicate-native-reference
rejection. Both new identity specifications failed before the source fix.

Focused owner/consumer/corruption regression: 110 passed before adding reverse
order; reverse-order focused file: 8 passed. A read-only real traversal reduced
all 28,350 physical observations in 21,620 partitions without identity failures
in 65.648 s, RSS 224.95 MiB. Concurrent scale/regression execution measured the
56,700 fixture at 42.793 s (read 17.062, reduce 4.347, completion 0.689,
completed lookup 0.0033 s); this contended measurement is not a performance
pass or a comparison with the previous isolated measurement. Packaged final
ready and unchanged-input evidence remain mandatory and are not yet proven.
