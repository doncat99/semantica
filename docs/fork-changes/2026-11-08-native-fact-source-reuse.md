# Native fact decisions and source reuse

- Record ID: 2026-11-08-native-fact-source-reuse
- Date / author: 2026-11-08 / repository contributor
- Status: verified-in-stated-scope
- Fork base revision: 76c81d2ea57542c02778559a9de019743a68b6d0
- Upstream reference: not refreshed; no new upstream capability claim
- Related issue / commits: pending commit; OntoScience deep relationship remediation

## Reason and scope

Completed source work and fact decisions were being reconstructed on normal reads and new publication generations. Fine-grained reads, repeated endpoint restoration, and transport-sized durability checkpoints amplified cold processing. Repair the existing native owners without changing qualified-fact semantics or copying paid results.

## Native capability assessment

Existing owners inspected: EntityMerger.merge_qualified_fact_group, ExtractionRecords, ClassificationRecords, QualifiedFactIndex and PublicationRecords. Actual semantic_publication_builder callers, canonical page consumers, source classification context preparation and connected tests were checked. Decision: repair these owners in place. No alternate reducer, engine, dependency or fallback is introduced.

## Approach and actual changes

- Source projection stores bounded address-only records in ExtractionRecords; no quote/body or paid-fact copies. Exact completed identity bypasses projection work.
- ClassificationRecords indexes its accepted source reduction before context construction. Cold context batching uses geometric search rather than repeatedly serializing every prefix.
- QualifiedFactIndex stages selected native entry references, status and evidence; canonical reads restore the selected observation once and never invoke the reducer. Forward partition traversal and bounded endpoint lookups replace repeated broader queries.
- PublicationRecords preserves completed fact decisions independently of generation; mismatched input resets only derived fact state. Sealing checks selected entry provenance, kind, observation and decision coverage. Staging retains membership, endpoint and unique-assignment checks.
- Each mutation remains bounded to 256KiB. Streaming durability checkpoints occur every 128 writes (at most 32MiB serialized input) and at normal scope exit. Completion markers follow flush; cancellation or exceptions leave pending output, never a reusable partial completion.
- Removed unused mutation extra-filter argument and obsolete read-time reducer calls/duplicate support bodies. No new public export or dependency.
- Existing paid results and receipts are unchanged; no live migration or user-data mutation performed. Older incomplete derived stages are rebuilt within their existing owner on demand. New completion indexes initially miss and populate once.

## Verification and limitations

- Connected focused selection: 110 passed in 77.64s; /tmp/native-repair-final-focused.log. Covers classification budgets/completion, projection corruption, fact semantics, cancellation, restart and publication activation, plus native consumers.
- Persistent target-scale fixture: 56,700 observations / 21,620 groups. Index 38.148s, reduce/stage 69.682s, seal 26.449s, completed lookup 0.000336s; total measured stages 134.278s. 180s gate passed; test including setup/teardown 151.09s. /tmp/fact-scale-checkpoints.log.
- Earlier same-scale attempt before checkpoint correction: 222.77s; transport-sized flush checkpoints were a measured amplification. Native-load experiment was discarded because it did not address this root cause.
- Target-scale fixture uses synthetic native observations and a lightweight projection reader; it does not measure live ESG storage hydration, model quality, whole-App duration, process RSS limits or a latency distribution. No claimed live performance acceptance.
- Real model calls, real-user build, migration and final App/Case acceptance not run at this record point.

## Upstream merge assessment

- Disposition: pending; current fork-specific qualified semantics and native persistence consumers must remain aligned.
- Incoming upstream revision: not reviewed in this change.
- Overlapping owners: entity_merger and triplet_store/publication/extraction/classification/index.
- Retain only while single native ownership and exact provenance constraints hold; adapt to equivalent upstream capabilities rather than retain parallel paths.
- After merge run the connected 110-test selection and serial target-scale fixture before packaging.

## Dated follow-ups

2026-11-08: performance evidence applies only to isolated native storage/reduction; packaged and real-data outcomes must be recorded separately.


## 2026-11-08 completion ownership and demand reads follow-up

Inspected base: `aabae908` on fork `main`. Repaired the same owners and actual builder consumers; no additional engine, body store or dependency.

- Fact index updates compare native observation identity, canonical conflict partition, representation, evidence and raw status. Only changed/removed old and new partitions lose decisions. Dirty decision references survive interrupted replacement; unrelated decisions remain physically unchanged. Functional-predicate policy has its own bounded identity and dirties only predicates whose policy changed.
- `begin` preserves fact completion and dirty state independently of identity-stage completion, including an interrupted later identity attempt. Red regression failed with missing fact completion; both completed/interrupted identity variants now pass after reopen.
- Canonical pagination removed the obsolete reducer callback entirely. Native reopened-store reads consume selected observation fields and saved decisions only.
- Warm source projection uses a position-zero header seek and lazy address references. Evidence subsets use bounded indexed seeks; passage iteration uses its position index. Missing address indexes fail explicitly and require the existing maintenance CLI `--index-source-projection`. That offline operation writes reference indexes only, never paid facts or bodies; interrupted indexing leaves no completion marker. Ordinary verification remains read-only.
- Classification assembly consumes only requested evidence IDs after one cold preflight. Completed classification lookup still precedes context/prompt construction. Fact projections return plain field dictionaries rather than constructing and dumping two Pydantic DTOs before use.
- Entity-backed object identities are unchanged. Literal-only assertion identities now encode literal type and value separately from entity IDs. Historical literal-only derived decisions require explicit recomputation within the fact owner before reuse; no paid extraction or receipt changes. The current native relation builder is entity-backed, so this distinction does not rewrite its existing fact IDs.

Evidence: connected selection 124 passed and one new offline CLI test failed from a test observer retaining the Oxigraph handle; corrected isolated CLI test passed in 0.87s (`/tmp/native-offline-cli.log`). Cancellation/generation and canonical publication selection: 41 passed in 16.64s (`/tmp/fact-generation-green.log`). Typed object identity and classification records: 20 passed in 6.05s (`/tmp/fact-typed-green.log`). Another connected selection: 70 passed, one new typed fixture failed ID validation; only the fixture IDs changed before the 20-test passing run. Skipped tests are not counted as passes.

Latest persistent target-scale fixture: 56,700 observations / 21,620 groups; index 54.392s, reduce/stage 73.341s, seal 26.943s, completed lookup 0.000367s. Measured stages total 154.677s; existing 180s gate passed. Test with fixture lifecycle 174.47s. Process time: real 175.03s, user 263.34s, system 23.02s; max RSS 1,316,077,568 bytes, peak footprint 1,614,205,504 bytes (`/tmp/native-final-scale.log`). These are synthetic lightweight-reader results, not live ESG hydration, activation p95 or whole-App resource acceptance.

Remaining scope: initial grouping reads minimum native index fields, then dirty-group consumption rereads selected native observation fields; the strict single-physical-read requirement is not proved. Existing report reuse still prepares grounding context before its report lookup. Real historical projection indexes have not been migrated; live ESG has not been restarted. The current request schema has no user functional-policy/withdrawal configuration, so no nonexistent input wiring is claimed. Final packaged Case outcome must be recorded separately.


## 2026-11-08 target-scale profile: performance rejected

The existing 180s test threshold is not product acceptance. The user explicitly rejected the 154.677s result. Packaging was stopped for diagnosis; no live build or model call was started.

Same test and revision `916ec8bc`, with cProfile: index 72.527s, reduce/stage 97.711s, seal 35.444s, completion lookup 0.000299s. Instrumentation increased measured stages to 205.682s and caused the existing 180s assertion to fail. These times must not be substituted for the unprofiled baseline or interpreted as a new regression. Test lifecycle was 224.33s. Raw evidence: `/tmp/native-fact-scale-profile.pstats`, `/tmp/native-fact-scale-profile.log`.

The fixture expands 56,700 native observations into 113,400 assertion/relation index entries. Across the diagnostic run there were 109,444,566 Python/native calls, 5,765,679 `quads_for_pattern` calls (49.812s native self time), 3,730,734 `values` calls (30.458s Python self time, 62.806s including children), 51,715 SPARQL updates (41.753s), and 245 flushes (10.918s). These categories have nested calls: do not add `values` cumulative time to its native child time. Fixture `extend` consumed 15.131s outside the measured stages.

- Index 72.527s: bounded entry flushes 26.090s; `_dirty` 113,400 calls / 16.613s, including 21,620 separate dirty writes and 21,620 separate previous-decision capture updates; `member` checks 4.512s; direct `values` 4.806s; batching including the synthetic reader 2.991s. `partition` is recomputed 340,200 times (2.681s). These are child timings and not a complete additive partition of the index stage.
- Reduce/stage 97.711s: `_reference_pages` 24.632s (567,001 `one` calls taking 14.140s); `stage_reconciled` 30.000s (4,722 selection writes plus 2,020 status writes; their mutation work 11.385s and 4.354s); `stage_facts` 21.481s; `_reconcile_partition` 18.962s, of which the semantic reducer is 6.807s. The reducer includes merger time and must not be added to it. The selection staging limit counts triples as rows, fragmenting each bounded decision batch into many SPARQL updates.
- Seal 35.444s: 1,587,601 `one` calls 24.686s, 226,802 additional `values` calls 3.452s, and 226,801 direct pattern seeks 1.683s. The same decision and selected-entry provenance are rechecked for every support entry. Three aggregate queries combined cost 1.325s; the direct seal flush costs 0.048s. The per-entry provenance reconstruction, rather than those aggregate queries or that flush, dominates sealing.
- Publication mutations invoke the full status/generation fence twice per mutation (60,162 calls / 7.141s), while the entire run invokes fence 86,753 times / 10.185s. Validation and generation safety must remain, but repeated full status materialization is avoidable.

Diagnosis: the dominant amplification is the fork-specific index/publication integration, not intrinsic complexity of qualified conflict semantics. Shared physical observation fields are indexed through two logical views; metadata is serialized into small SPARQL updates; readers reconstruct fields with millions of scalar point reads; sealing repeats decision validation per supporting entry. Flush tuning alone cannot fix this. A subsequent repair must preserve exact trust-boundary validation, membership/endpoint/unique-assignment invariants, bounded bytes, cancellation and durable completion, while removing the repeated physical work. No performance source change or improved latency is claimed by this diagnostic record.

## 2026-11-09 compact references and bounded native ingestion

Inspected base remains `916ec8bc`, fork `main`. The same QualifiedFactIndex,
PublicationRecords and builder callers are repaired in place. ConflictDetector
and EntityMerger remain the semantic owners; no new engine, cache, certificate,
dependency or ESG-specific branch is added.

- Logical assertion and relation observations retain independent identities and
  semantics. Their reference fields are stored in one compact validated record
  per logical slot, rather than reconstructed from multiple RDF scalar fields.
  Subject, predicate and selected evidence query indexes belong to the completed
  decision. A support-observation-ID index was also removed: actual support
  consumers traverse existing entry-to-decision membership, with row/byte bounds
  and identity checks, without calling the reducer or restoring support bodies.
- Native reference pages enforce both 128 rows and 256KiB serialized bytes.
  Partition references are bounded before DTO hydration (default 4,096 logical
  entries and 16MiB); hydrated observations retain their separate byte check.
  Oversized partitions fail explicitly before producing partial semantics.
  These are supported-operation limits, not evidence of unlimited fanout.
- Decision/fact output streams into native RDF ingestion. Each native loader
  receives at most 128 input batches, each at most 256KiB (32MiB input total).
  This also bounds native sorting input independently of project size. The
  installed pyoxigraph 0.5.13 bulk API exposes no memory/thread budget; its Rust
  loader's default memory target is large and excludes RocksDB/system overhead.
  Therefore 32MiB is an input bound, not a process RSS guarantee. Native memory,
  store cache, and compaction still require process measurements.
- Sealing reads compact entry records, shares decision projections within a
  bounded page and checks exact member-to-decision correspondence. Equal counts
  with swapped or duplicated members are rejected. Required endpoint, subset,
  unique ownership, status, cancellation and durability checks remain.
- Existing completed result reuse still returns the completed reference. This
  correction does not authorize re-extraction, copying paid results or changing
  business identity because of a source/artifact digest.

Consumer/storage contract: build and seal necessarily traverse current native
observations; canonical reads select completed decisions and requested support
members only. No completed-read reducer callback is retained. Growth tests cover
both one repeated-support partition and distinct partitions at 32/128/512 native
observations. At each fourfold growth, measured native pattern seeks and stored
triples remain at most fourfold plus fixed overhead. Both logical views read
exactly once per observation during cold reduction; completed support reads are
separately bounded. This proves those tested work bounds, not whole-App latency
or resource scaling for arbitrary data distributions.

Regression evidence: support-index deletion first failed on retained duplicate
triples (`/tmp/fact-support-red.log`); reference-page byte bounds first failed
before repair (`/tmp/fact-page-bytes-red.log`). The native-ingestion-window test
first observed one 129-batch load instead of 128+1 (`/tmp/fact-import-bound-red.log`).
Final connected owner selection: 97 passed in 39.42s
(`/tmp/fact-generic-bounded-focused.log`). Tests include conflict/withdrawal,
functional predicates, typed identities, exact coverage corruption, cancel,
reopen, incremental invalidation, byte limits and both growth distributions.

Before the native ingestion window was bounded, the final same-scale diagnostic
measured index 14.951s, reduce/stage 48.715s, seal 17.267s, warm completion lookup
0.000495s; measured stages total 80.934s. Test lifecycle 100.79s; maximum RSS
1,101,299,712 bytes and peak footprint 1,592,807,936 bytes
(`/tmp/fact-generic-final-scale.log`). This is not acceptable performance delivery
and is not the final bounded-ingestion measurement. Earlier 66.982s and 78.972s
runs had different instrumentation/load conditions; no stable speedup ratio or
p95 is claimed.

Migration/reset boundary: old scalar-only derived indexes must be explicitly
reset through the current fact-stage owner before rebuilding; there is no old
format reader or normal-read migration. Reset only derived fact/index decisions,
after stopping readers. Original material, paid extraction facts, vector rows,
user edits and receipts are outside this reset. No live user store was changed.

Case delta: `journey-library` keep; primary owner remains
`e2e/ui/library-knowledge-mainline.test.ts`. These isolated storage tests are
supporting evidence. Packaged App, live ESG, change-verification, target-scale
p95 and larger-project RSS acceptance remain unverified. Prior report-context
reuse and historical source-projection migration gaps are not closed here.

Final bounded-ingestion target-scale run: index 19.844s, reduce/stage 45.137s,
seal 24.283s, warm lookup 0.000204s; measured stages total 89.264s. Test lifecycle
105.23s; maximum RSS 1,153,187,840 bytes and peak footprint 1,589,416,640 bytes
(`/tmp/fact-generic-windowed-scale.log`). The existing 180s regression alarm
passed, but this remains rejected performance, not product acceptance. The
window limits each loader's input; it did not demonstrate reduced process RSS
at this scale, and is not presented as a speed optimization. These measurements
include fixture construction in process RSS and lifecycle timing; stage timings
exclude fixture setup. No larger-project memory bound or performance p95 is
inferred from them.

## 2026-11-09 review correction: eliminate work amplification before tuning I/O

Status: reviewed and measured; replacement below is a design requirement, not
implemented or qualified. Native owners remain QualifiedFactIndex,
PublicationRecords, ConflictDetector and EntityMerger on main. Existing dirty
implementation and historical evidence are preserved.

A fresh instrumented run of the current test at 5,670 native observations and
2,162 partitions (one tenth of the target fixture) measured index 1.672s,
reduce/stage 4.665s, seal 1.834s. The fixture's printed 56,700 label is constant;
it does not describe this diagnostic's actual input. cProfile includes setup
and instrumentation, so do not extrapolate an exact target-scale latency.
Evidence: /tmp/fact-review-current.py, /tmp/fact-review-current.log and
/tmp/fact-review-current.pstats (isolated temporary store; no live data/models).

Observed work: 144,805 publication-predicate triples including small initial
fixture metadata, 11,340 compact logical records, 38,435 compact-record decodes,
186,327 native pattern seeks and 214,613 JSON dumps. Semantic reconciliation's
inclusive profile cost was 0.588s. bulk_load inclusive cost was 5.774s, of which
4.935s was nested Python stream-production callbacks; native self time was
0.839s. These nested costs must not be summed. The evidence contradicts treating
bulk loader time as disk time or treating the reducer as the dominant cost.

Blocking design findings:

- build writes two logical work records per physical observation, followed by
  full reference traversal, native rehydration, DTO conversion, decision/fact
  staging and another per-entry sealing traversal. Compact JSON reduced field
  count but preserved the materialize/read/restore/revalidate pipeline.
- The reducer boundary converts dictionaries into models, back into dictionaries,
  and back into models; representative selection serializes the same complete
  observation in both the index and merger. Required semantics do not justify
  these repeated representations.
- _fact_triples revalidates native ownership, endpoints and identity fields after
  input admission; seal_fact_stage reconstructs the intermediate graph again.
  Trust-boundary checks and exact coverage remain required, but a private single
  producer must not repeatedly rehydrate the same immutable input to prove them.
- Incremental build rewrites qualifiedSeen even for unchanged entries and scans
  all entries for removals. _reference_pages decodes clean partitions too.
  The completed-stage fast path does not make a small input change incremental.
- A 32MiB bulk-loader input window is not a native process-memory budget.
  A 4,096-record partition rejection is a failure guard, not a scalable solution
  for legitimate high-support groups. Current scale fixture also substitutes
  synthetic read DTOs for the actual builder's native hydration and includes
  fixture construction in process peak RSS.

Replacement requirements within these same owners:

1. One physical observation admission/projection. Preserve independent assertion
   and relation identities as explicit slots and mappings, without two complete
   intermediate records or duplicate source/status/evidence payloads.
2. Use existing native membership/index traversal to group by semantic identity;
   reduce each distinct proposition once and check conflicts among distinct
   propositions. Stream support references. Do not build support-sized DTO lists
   or add a second persistent engine/cache. Large groups need streaming reduction
   and paged support/evidence output rather than a larger group limit.
3. Keep one minimal reducer input through ConflictDetector/EntityMerger; schema
   validation at admission and actual external output boundaries. Preserve typed
   values, qualifiers, polarity, functional-predicate rules, withdrawal, exact
   representative selection and all evidence references.
4. Store completed decisions and direct native member references. Remove
   qualifiedRecord/qualifiedSeen work carriers and redundant selected-entry
   metadata only together with all readers, integrity tests and reset selection.
   Validate exact reference-to-decision mapping once under the generation fence;
   durability and activation cannot substitute equal counts for exact membership.
5. Derive incremental dirty scope from old/new input membership and canonical
   endpoint dependencies. Clean inputs and partitions must have zero rewrites,
   native DTO hydration and reducer calls; removals must not require touching
   every unchanged observation.
6. Measure the real native projection as well as the synthetic reducer fixture.
   Separate baseline store RSS, stage peak/delta, CPU, native seeks, records and
   bytes; include repeated-support, distinct-proposition and skewed large-group
   distributions. Input batching alone proves no process RSS bound.

Do not spend another target-scale run on batch size changes. First demonstrate
removal of the intermediate carriers and repeated hydration in focused physical
work specifications, then measure the connected replacement at target scale.
Existing 180s alarm is not an accepted performance budget. No new App, live ESG,
change-verification, production migration or release acceptance is claimed.

## 2026-11-09: validated observation mapping

`ConflictDetector.reconcile_qualified_facts()` now validates each native
observation once with its owning Pydantic schema and passes the validated
model's field mapping directly to `EntityMerger`. The former per-view
`model_dump()` deep serialization was removed; qualifier, typed-value and
schema validation remain at the same admission boundary. The reducer still
selects the lexicographically minimum canonical observation and preserves
withdrawal, polarity, evidence and support references.

Focused fact/publication tests: 109 passed after widening one query-observation
fixture to accept the separate bounded endpoint ownership query already used by
the staging owner. This is not target-scale acceptance; the 56,700-observation
fixture remains above the required performance budget.

## 2026-11-09: exact endpoint seeks and bounded operation admission

Native owner: `PublicationRecords._fact_triples`, on fork `main` at
`916ec8bc` plus the current working changes. The former endpoint-membership
query returned all members of each canonical endpoint, even when a staging page
needed only two native endpoints. Its ownership query also joined batch members
against every staged fact. These are scope amplification, not semantic work.
Both were replaced with exact native quad seeks, including inverse member seeks
before checking current fact ownership. Endpoint uniqueness, qualifiers, native
record ownership and cross-fact duplicate rejection remain enforced.

The unrelated-endpoint regression returned 2,054 rows before the fix and now
requires fewer than 200 despite 2,000 unrelated members. The full-page staging
specification now requires zero SPARQL queries. Focused publication/index tests
passed: 110 tests before the subsequent admission-page change below.

One instrumented 56,700-observation / 21,620-group run after the exact-seek fix:
index 17.372s, reduction/staging 35.166s, seal 10.258s, completed reuse 0.000163s;
stage total 62.797s. Reduction/staging was 109.84s in the earlier run. The total
still fails the requested performance outcome. Method timings are nested and
must not be added: `_fact_triples` 12.577s, `field_page` 8.795s, reducer 7.547s,
`member` 6.664s and qualified-record decoding 5.533s. Raw local evidence:
`/tmp/fact-exact-membership-timed.log`. This synthetic fixture excludes actual
builder hydration; it does not qualify App performance or process RSS bounds.

A subsequent repair adds bounded `PublicationRecords.members` admission and
routes the existing single-record `member` through the same implementation.
Each record still seeks its actual native owner. Only successful operation
admission is shared within a maximum-128-record call; no state survives the
call. Index admission, endpoint pages and fact staging use this page boundary.
The regression verifies shared admission once and rejection after its source
binding is removed. Decision partitioning also consumes validated model fields
directly rather than serializing the whole selected observation.

No real user data, model calls, immutable pins, packaged App or release state
were changed. Larger intermediate-carrier replacement and skewed-group memory
bounds above remain open; these changes must not be represented as completing
that architecture work.

Admission-page focused verification: 118 tests passed in 57.68s across
canonical fact publication, qualified fact indexing, publication records and
support-copy residency. A further red/green regression forbids `model_dump`
inside semantic reconciliation and decision staging; it exposed two remaining
whole-assertion serializations solely to read the typed object. Those now read
the validated mapping. The regression exercises opposite polarities and stages
both view decisions; it passes after the repair. External serialization remains
at its output boundaries.

Post-admission instrumented target run (`/tmp/fact-page-admission-timed.log`):
index 14.653s, reduction/staging 31.223s, seal 17.343s, reuse 0.000376s;
stage total 63.219s. This does **not** demonstrate an overall improvement over
62.797s: reduced admission/staging cost was offset by slower sealing. No
statistical speedup claim is made from these single runs. The wrapper counts
single-record `member` calls only; the new page method's native seeks remain,
so the smaller function-call counter is not evidence of eliminating all native
ownership reads. Qualified reference decoding still occurs 226,800 times and
reference-field reads remain; removal of redundant intermediate carriers is
still required for the overall objective.

Final focused verification for this iteration: conflict suites, native conflict
access, qualified index and canonical publication (excluding already-run
activation tests): 113 passed, 2 deselected, 31 subtests passed in 27.47s.
`git diff --check` passes. Existing `journey-library` Case contract/baseline is
unchanged; delta is keep. Native focused tests are supporting evidence only;
App-level primary Case and change-verification have not been rerun or passed.

### 2026-11-09: address-scoped sealing and storage field projection

Native owners remain `PublicationRecords.seal_fact_stage` and `field_page`;
callers are qualified decision completion and `_fact_triples`. Sealing now
streams each bounded decision page's reference literals with its membership
edges, instead of issuing one `qualifiedRecord` point read per logical view.
Missing literals remain visible through OPTIONAL and are rejected; duplicate
literals/entries, wrong identity/partition, selected-reference absence, relation
membership substitution, status and exact coverage checks remain enforced.
The existing completion traversal regression now also prohibits those point
reads. The publication/index/canonical suites passed 112 tests in 40.61s.

Instrumented target run `/tmp/fact-streamed-seal-timed.log`: index 10.788s,
reduction/staging 32.691s, seal 16.893s, reuse 0.000172s; total 60.373s.
This is still inadequate and does not demonstrate a large speedup. A separate
10,000-observation/4,000-group cProfile run identified `field_page` as a large
Python/native iteration cost: it requested selected fields but read **all**
fields of each addressed record before filtering. Evidence is local at
`/tmp/fact-small-profile`; profiling overhead and the smaller fixture prevent
using these times as target-scale qualification.

New red/green regression adds 2,000 unrequested fields and verifies that reading
one status materializes exactly one result row. `field_page` now binds both
subject and predicate in native index seeks, retains its existing row/byte
checks and never enumerates unrequested fields. An attempted double-VALUES
SPARQL projection selected an expensive plan at target scale; that isolated run
was terminated and the attempted implementation removed. The existing full
member-page staging regression retains zero SPARQL queries and its total native
read budget. Six focused projection/staging tests passed in 4.15s.

No storage format, user data, model execution, artifact pin or App state changed.
The repeated qualified-record carriers/decoding and full App acceptance remain
open. This repair must not be described as completing that replacement.

Follow-up target run `/tmp/fact-indexed-fields-timed.log`: index 11.020s,
reduction/staging 34.026s, seal 14.303s, reuse 0.000409s; total 59.350s.
It remains over the required performance objective.

The single-record `fields` caller still enumerated all support fields before
filtering. Its red regression materialized 2,001 rows for a one-status request.
It now delegates to the same bounded address/predicate projection: one row,
including when many unrelated support fields exist. Both affected callers
(existing fact-plan validation and incremental reference comparison) use it.
The four focused suites passed 121 tests in 43.00s after this change.

Reference paging and partition byte accounting also reserialized every parsed
reference tuple twice. The private page iterator now carries the already
persisted UTF-8 byte length alongside the validated reference. Both row and
byte caps remain, including rejection before hydration; no persistence format
or public API changes. A red/green specification forbids reference tuple
reserialization and the existing byte-budget test verifies exact stored sizes.

`/tmp/fact-reference-bytes-timed.log`: index 10.568s, reduction/staging 27.424s,
seal 9.617s, reuse 0.000353s; total 47.609s for the same synthetic target.
This single run is not a statistical speedup qualification. Timers are nested:
`qualified_record` now receives literals read by its caller, so its smaller
reported self-wrapper time must not be interpreted as eliminating those reads.
The fixture excludes production builder hydration and App startup. No RSS
hard bound, skewed-group qualification, immutable App artifact, primary
`journey-library` or change-verification pass is claimed. Case delta remains
keep; existing product gates and baseline are unchanged.

### 2026-11-09 follow-up: exact sequential completion membership

Owner remains `PublicationRecords.seal_fact_stage`; no new storage format or
result owner. A red specification forbids a per-support member seek. Completion
now traverses each relation decision's members once and consumes its already
bounded expected-reference set. It rejects missing, extra, foreign and non-IRI
members, including equal-cardinality replacement; it does not rely on counts
alone. This makes the later per-fact member-count GROUP BY redundant, so that
query was deleted. Cross-fact duplicate detection and total fact coverage
checks remain. No completion marker is written on the new corruption cases.

The new three cases passed (valid, foreign replacement, same-value literal
replacement). Four affected storage/reducer suites: 125 passed in 43.77s.
Production builder boundary suite: 7 passed in 13.62s, including single physical
observation restoration and completion reuse. `git diff --check` passed.

Target run `/tmp/fact-exact-members-timed.log`: index 13.545s, reduction/staging
33.120s, seal 9.738s, reuse 0.000207s; total 56.403s. Compared with the preceding
47.609s single run this demonstrates no further speed improvement; do not claim
that removing member seeks repaired the performance problem. The prior nested
wrapper counts still show 226,800 reference decodes, 321,077 scalar lookups,
and 22,405 field-page calls. A scratch UNION-projection experiment on only
10,000 observations was not adopted and is not target-scale qualification.

The repeated intermediate logical carriers, native field reconstruction and
write path remain the larger unresolved work. Neither the synthetic timeout
nor these supporting passes are the product performance gate. No user-data
migration, model call, App snapshot/package, pin update or real ESG execution
was performed. Primary Case `journey-library` and change-verification remain
unrun for this source candidate; Case delta keep, baseline unchanged.

### 2026-11-09 follow-up: bounded physical projection field lookup

Inspected native owner `ExtractionRecords._read_fact_projections` at current
`main` (HEAD `916ec8bc`, with the existing uncommitted remediation). Callers
are `read_fact_projections`, `read_fact_index_projections`, single-view reads,
and the builder's first-time fact-index/reduction paths. The owner was scanning
its entire bounded Quad list for every scalar and every evidence position and
reference. A 128-evidence red specification observed 159,324 Quad attribute
accesses for one physical observation.

Replaced repeated list scans with a lookup populated while the same projection
is read. It exists only for this read, under the existing 1,024-Quad and byte
limits; no durable cache, additional storage owner, format change or migration.
Digest verification, required/optional field cardinality, evidence ordering,
source ownership and both logical view outputs are preserved. No raw fact,
result or receipt is copied. The red spec now passes its <5,120 attribute-access
budget. Projection and qualified-index owner suites: **71 passed in 32.40s**,
including restart, source-observation oracle and completed-decision reads.

Read-only microbenchmark against the pre-change owner from HEAD, same real
Oxigraph fixture, 200 both-view reads per sample, three samples each (median):

| Evidence references per observation | Before | After |
| --- | ---: | ---: |
| 1 | 0.0735s | 0.0645s |
| 16 | 0.4948s | 0.2674s |
| 128 | 5.7659s | 0.6344s |

Raw local evidence: `/tmp/fact-projection-read-bench.log`; scratch runner:
`/tmp/fact-projection-read-bench.py`. This is a repeated-read microbenchmark,
not a cold-store or full-build performance qualification. The prior 56,700-row
synthetic runner does not hydrate these physical projections, so its earlier
47–56s figures cannot be reduced by extrapolating this result. Its unresolved
intermediate carrier, native reconstruction and staging costs remain open.

A separate attempted partition-wide SPARQL stream for qualified reference
records was rejected and reverted: index 11.309s, reduction/staging 36.511s,
interrupted during seal (`/tmp/fact-stream-reference-timed.log`). Fewer Python
point reads did not produce a speed improvement; no such query change remains.

Upstream assessment: this repairs the existing fork projection owner in place;
upstream does not provide a replacement for its source-observation contract.
Case `journey-library`: delta **keep**, existing baseline/hard gates unchanged.
Primary App acceptance and change-verification are **unrun** for this candidate.
No user data, paid calls, artifact pin or installed App was changed. No final
build-performance or release-completion claim is made.

### 2026-11-09 follow-up: one admission per observation and cold-plan seeks

At `main` HEAD `916ec8bc` plus the existing working changes, inspected
`QualifiedFactIndex._reconcile_partition`, `ConflictDetector.reconcile_qualified_facts`,
`EntityMerger.merge_qualified_facts`, and `PublicationRecords._fact_triples`.
The index serialized every body for its byte bound and computed its canonical
identity; the reducer then repeated both operations for the same observation.
The existing merge now exposes synchronous admission of its schema-validated
mapping, canonical identity and exact UTF-8 selection-encoding length before
accumulation. The index performs its existing address, partition, identity and
byte checks at that boundary. Selection order, schema validation, qualifiers,
withdrawal, support references and conflicts remain in their original owners.
No additional stored records, certificate, cache or schema are introduced.

The new red specification
`test_reduction_serializes_and_identifies_each_observation_once` observed two
body encodings per input before the fix; now it verifies one encoding and one
canonical identity computation per observation. Existing byte-limit, changed
identity, representative-selection and conflict-oracle specifications pass.

Cold fact staging also previously probed five plan fields when the result node
did not exist. A native address-existence seek now avoids restoring absent
fields; existing/orphan fields still undergo the unchanged plan comparison.
Role admission uses one inverse head/address seek instead of three independent
role probes, with an explicit 128-role fanout limit. Red/green tests verify the
physical seek and absent-field behavior, all other role collisions, and rejection
of a contradictory orphan plan. No persisted format or data migration changes.

Validation: 164 selected checks passed; six checkpoint checks initially exposed
an accidentally displaced `@contextmanager` during editing. The decorator was
restored immediately; those six checks were rerun and passed (3.01s). Selection:
publication records, canonical fact publication, qualified fact index, support
residency, project fact identity and kernel owner regressions. This is focused
source validation, not App acceptance.

Rejected scratch experiments: bound-node UNION and wide OPTIONAL projections
were slower than exact native seeks; explicit `(node, predicate)` VALUES rows
were also slower (30 samples of one bounded page: 0.421s versus 0.329s). None
was adopted. The intermediate admission-only target run measured index 12.344s,
reduction/staging 27.108s, seal 13.709s, reuse 0.000184s; total 53.161s. Its
reduction time improved against the previous single 33.120s run, but aggregate
variation does not establish a whole-stage performance fix.

Final cold-admission candidate: `/tmp/fact-cold-admission-scale.log`, persistent
Oxigraph synthetic fixture, 56,700 physical observations / 113,400 views /
21,620 partitions. Index **15.403s**, reduction/staging **29.991s**, seal
**9.582s**, completion reuse **0.000199s**; timed stages **54.976s**.
`/usr/bin/time -l` measured 70.47s process wall time (includes fixture setup and
teardown), 67.91s user CPU, 5.86s system CPU and maximum RSS **1,150,205,952
bytes** for the whole test process. These measurements neither establish bounded
production RSS nor qualify the requested performance budget. The timeout test
passing is not performance acceptance. Across the earlier 47–56s range, this
candidate has **not demonstrated a substantial aggregate speed improvement**.
Remaining intermediate view carriers and repeated native reconstruction are
still unresolved; do not extrapolate the projection microbenchmark to this
cold build. No user-data migration, paid model call, App packaging, pin change,
commit or push occurred in this continuation. Case `journey-library`: keep;
primary product run and change-verification unrun, baseline unchanged.

### 2026-11-09 continuation: seal adjacency and bounded native observation reads

Inspected native owners on `main` at inherited HEAD `916ec8bc`: extraction
projection admission (`ExtractionRecords`), qualified grouping and reduction
(`QualifiedFactIndex`), publication sealing (`PublicationRecords`) and the
publication builder's actual index/reduction callbacks. These repair the same
owners; no storage engine, persistent cache, proof record or migration is added.

Sealing now traverses native decision adjacency rather than materializing the
SPARQL support join. It still validates qualified-record address/schema,
partition ownership, selected membership, status and exact physical support
membership, including equal-count substitutions. Five corruption/adjacency
specifications pass (`/tmp/fact-seal-native-defects-green.log`); original red
runs are `/tmp/fact-seal-native-red.log` and
`/tmp/fact-seal-literal-red.log`. Target-scale result before the page-reader
change: index 10.589s, reduction/staging 26.548s, seal 8.336s, reuse 0.000192s;
45.473s timed stages. Whole-process maximum RSS 1,124,630,528 bytes. This is
not performance acceptance, nor a proven production memory bound.

The synthetic scale callback does not open real extraction projections. The
production builder did: each physical relation opened its 11 binding fields,
validated the completion receipt, then validated that receipt again on the
projection read. The next relation repeated the operation admission.
`ExtractionRecords.read_fact_projection_page` shares operation admission only
inside a locked, cancellation-aware page (128 distinct native relations,
16 MiB total stored projection bytes, existing 256 KiB/1024-quad per-projection
limits). Each relation still checks native type/ownership; full reads retain
digest and ordered evidence validation. Another page admits the operation anew.
The existing lightweight grouping projection remains a field read; it is not
promoted to a full integrity audit. No payload or accepted result is copied.

The builder index now uses that page owner. The qualified reducer callback now
accepts one ordered page of `(reference, kind, observation)` keys, returning
matching observations. All production callers and fixture readers are updated;
there is no scalar/page dispatch or compatibility reader. The builder resolves
unique physical references and canonical endpoints once per page instead of
opening each view individually. Existing partition/identity admission and
semantic reduction are unchanged. The support-body retention specification
now permits one 128-view page plus three reducer boundary references, rather
than the former scalar-reader three-reference bound; the previous page is
explicitly released before reading another. This is a deliberate bounded page
tradeoff, not a claim of lower total process RSS or permission to retain groups.

Evidence so far: page red `/tmp/fact-projection-page-red.log`; 112 affected
checks passed before reducer callback conversion
(`/tmp/fact-projection-admission-regressions.log`). Real accepted projection
read microbenchmark, 128 relations from one operation, ten repetitions:
scalar 1.133360s / 2,560 receipt reads; page 0.170541s / 10 receipt reads
(`/tmp/fact-projection-page-bench.log`). This includes full projection digest
checks, excludes fixture creation, and does not measure the whole fact stage.
Reducer page red `/tmp/fact-reducer-page-red.log`; two page/retention checks
pass (`/tmp/fact-reducer-page-residency.log`). The first combined callback run
had 99 passes and the old scalar retention expectation failed; it was updated
to the explicit page bound above. Final affected regression/scale results
follow below. Upstream merge impact: preserve the current batch read contract
and exact checks when merging; do not restore per-view receipt admission.
No user-data mutation, model call, App qualification or baseline change.


### 2026-11-09 correction: remove the intermediate mechanism completely

This section supersedes the callback/intermediate-layout description above;
previous measurements are historical evidence, not qualification of this path.
Inspected inherited fork `main` HEAD `916ec8bc`, the actual builder caller,
`QualifiedFactIndex`, extraction projection owner, publication sealing and all
canonical-page consumers. Replaced those owners in place.

- Removed temporary SQLite/file generation, writes, reads and cleanup from fact
  reconciliation. Removed persisted per-observation dual-view entries and the
  old build/read/reduce callback APIs. No alternate spool, cache or engine replaces
  them. Scratch experiment scripts identified for this implementation were
  removed; unrelated files and user stores were not deleted.
- The sole path is native relation references -> full bounded projection pages
  -> one bounded semantic conflict group -> final decisions/member references.
  Both semantic views exist only during bounded computation. The existing
  ConflictDetector/EntityMerger remains the sole semantic owner. Qualifiers,
  polarity, functionality and all support references are preserved.
- Native reads fill 128-reference pages across group boundaries. A regression
  uses 140 distinct tiny groups and requires exactly two page reads (128, 12),
  avoiding per-group admission of the same operation. Group limits are 4096
  logical observations and 16 MiB input; native subject sort-key preflight
  rejects more than 128 MiB instead of silently truncating or spilling to a
  second store. These are explicit admission limits, not unlimited scalability.
- Only final decisions, selected fields, representation/evidence references,
  member references and publication completion metadata are persisted. A final
  relation decision directly references its final fact plan; an assertion
  records its final canonical target. This avoids string-derived broad joins,
  not a second observation representation. Exact native subset, unique ownership,
  cardinality, selected membership, predicate, endpoints and qualifier-set
  validation remains at seal; completion follows durability and generation
  fences. Normal completed reads never invoke reconciliation.
- Obsolete derived layouts raise an explicit offline-reset-required error.
  Existing `reset_fact_stage` is the migration boundary: reset derived decisions
  only, then recompute through the single owner. No compatibility reader exists.
  No live data reset/migration has been performed. Extraction, receipts and
  vectors are not copied or deleted by this change.

Verified source scope: 81 connected semantic/consumer/projection/build checks
passed in 33.65s before the final direct fact-plan adjacency refinement; 77
owner/publication checks passed in 19.87s before that refinement. After it,
33 direct owner checks passed in 4.64s, including no tempfile/sqlite creation,
no persisted dual-view entries, completed read zero reducer calls, cancellation,
restart, withdrawal and corruption rejection. `git diff --check` passed.
A 5,670-observation/2,162-group diagnostic measured build 4.911s and seal 3.027s;
this is not target-scale acceptance. Target-scale result is recorded below.

Auto Test: `journey-library` keep, pass criteria/baseline unchanged. These are
supporting owner checks; App primary Case and change-verification have not run.
No packaging, pin update, paid model call, user-data mutation or remote push in
this continuation. Upstream merges must preserve direct native consumption and
final-only storage; do not restore intermediate files or per-view entries.


Final serial target-scale measurement for this direct path (real accepted
native projections, persistent isolated Oxigraph store): 56,700 physical
observations / 21,620 groups. Native read 38.672s (included in build), semantic
reduction 5.175s (included in build), read/sort/reduce/final commit **67.669s**;
seal **48.519s**; completed lookup **0.000392s**. Timed build+seal **116.188s**.
The scale test **failed** the unchanged seal <5s gate. Whole test 132.41s,
`/usr/bin/time -l`: 133.04s real, 180.00s user, 23.55s system, maximum RSS
363,528,192 bytes. This lower measured RSS does not establish a universal
process memory bound. Temporary-file removal is implemented, but first-build
and seal latency remain unacceptable; no release/performance acceptance is
claimed. The small-scale seal timing must not be extrapolated to this scale.

Final connected source regression selection after the direct final-plan link
and endpoint-query fixes: **125 passed in 45.64s**. Includes native pipeline,
projection bounds/admission, completed consumers, support residency, fact
identity, canonical publication (including the existing 56,700-observation
activation budget), publication records and direct/no-temp-file owner tests.
This does not override the separate failed cold-build/seal scale test above.

### 2026-11-09 measured cost diagnosis after intermediate removal

Scope: diagnose the remaining latency in the existing QualifiedFactIndex,
ExtractionRecords and PublicationRecords owners, not introduce another store,
cache or reducer. Persistent fixtures are isolated and synthetic; no user data,
App rebuild, model invocation or release change was involved.

A target-size build (56,700 physical observations, 21,620 groups) was instrumented
with nested-child time subtracted. Generator timing surrounds each `next()`, not
the wall-clock lifetime between yields. Exclusive categories in seconds:

| Category | Calls | Seconds |
| --- | ---: | ---: |
| Final import | 516 | 16.282 |
| Fact projection pages | 443 | 15.384 |
| Canonical endpoint admission | 443 | 10.489 |
| Native reference iterator advances, including terminal advance | 56,701 | 8.852 |
| Semantic group reduction | 21,620 | 5.451 |
| Physical row assembly, excluding measured children | 56,701 | 2.619 |
| Publication field reads | 37,459 | 2.475 |
| Publication mutations | 1,034 | 1.301 |
| Identity binding admission | 444 | 0.300 |
| Flush | 526 | 0.100 |
| Identity projection | 444 | 0.064 |
| Fence | 446 | 0.007 |
| Unattributed orchestration / final triple generation | — | 3.596 |
| Total | — | 66.921 |

The former per-group fence and duplicate physical-page fence were replaced with
cancellation checks under the already-held publication lock. Endpoint-page,
entry and commit fences remain. This is a small redundancy removal, **not a
measured solution to the main bottleneck**: total latency remains approximately
67 seconds. The preceding 67.669-second run was not a controlled A/B trial.
77 focused index/direct-decision/publication tests passed in 20.45 seconds.

A separate target-size seal measurement fully consumed query results (including
boolean ASK results): 35 SPARQL queries, 52.311 seconds total. Categories:
decision/fact consistency 16 queries / 15.476s; endpoints 6 / 14.074s;
qualifiers 2 / 9.250s; observation identity 2 / 6.236s; predicate 2 / 3.973s;
cardinality 6 / 3.026s; owned input coverage 1 / 0.268s. These categories are
query-shape classifications, not storage-engine execution-plan row counts.
Negative ASK validation must exhaust its candidate matches; the two view loops
repeat physical-member validation and field-specific joins. This seal is from
a separate run, not an additive timing category inside the 66.921-second build.

An additional 5,670-observation / 2,162-group cProfile run recorded 4,837,784
function calls (6.542s with profiling), 88,738 native quads_for_pattern calls,
52 native bulk_load calls, 5 native query calls, and 83,222 triple() calls.
These are **small-fixture counts**, not measurements at 56,700. Native bulk_load
alone used 1.102s own time; fact projection recovery 1.357s cumulative; endpoint
pages 0.761s cumulative. The installed pyoxigraph bulk_load documentation states
that it always writes new disk files and targets big files; load is the
transactional small-input alternative. This establishes a mismatch between
hundreds of small final windows and the selected import primitive, not proof
that replacing it alone meets the budget. Flush itself is not the dominant cost.

Root cause is the storage/computation boundary: even with intermediate files
removed, native rows are joined/sorted for keys, then reopened through multiple
membership/endpoint/projection readers; projection reads enumerate RDF fields,
serialize quads, sort and recompute their digest; final reference decisions expand
into many RDF statements and repeatedly enter the bulk-file loader; seal then
rejoins original observations for each field and both views. The reducer is a
small fraction. Identity-projection reads and Pydantic are not the dominant
measured bottleneck in this implementation. Removing temporary storage did not
remove these independent amplification paths.

Required next implementation direction (not delivered/accepted by this diagnosis):
one admitted bounded physical observation carries the required endpoint, predicate,
qualifier and source binding through grouping; final selections/member references
are committed through a bounded transactional write path without intermediate
serialization round trips; exact commit invariants and completion checks must
have distinct responsibilities instead of per-view field-by-field repeated
revalidation. Preserve native subset, unique membership, endpoint/qualifier
consistency, corruption rejection, cancellation and restart safety. Any replacement
must retain the current semantic owner, existing budgets and final-only storage.
A raw COUNT equality alone is insufficient. No performance acceptance is claimed.

Auto Test remains journey-library / keep; baseline unchanged. Focused owner
checks are supporting evidence only. App Case and change-verification remain
unrun. Query-plan cardinalities, arbitrary skewed input scaling and filesystem
write-byte amplification have not been measured; small-fixture call counts must
not be presented as target-scale counts or a universal complexity guarantee.

### 2026-11-09 stage-wide streaming bulk import correction

User decision: this complete stage should use one large native import, not
hundreds of small bulk imports. `QualifiedFactIndex.reconcile_and_stage()` now
passes a single lazy final-triple stream to
`PublicationRecords.import_batches()`, which calls Oxigraph `bulk_load` exactly
once. The 256KiB windows bound Python serialization; they are not separate
imports or commits. No application intermediate file, full-stage Python list,
alternate reducer or data store was added. Oxigraph's own import buffers and
disk files remain implementation resources, not bounded by this Python window.

Final group signatures remain pending until the entire import returns, the
generation is checked and output is flushed. A single native update promotes
them only after successful import. A failed import cannot create a reusable
completion; existing partition ownership permits removal of an imported prefix
and recomputation on retry. Stream windows check cancellation. `bulk_load` is
not claimed to be atomic: only subsequent completion/publication is committed
after success. Tests cover interruption after a short prefix and just before
the final triple, restart/retry, generation fencing, oversize windows and one
import across 300 windows/multiple semantic groups.

Native traversal now carries source/target canonical addresses into the bounded
physical page, avoiding a second per-relation endpoint reader. Unique canonical
membership is still checked per distinct mention in each page. Full fact
projection admission and digest checks remain. Builder representation identity
continues to come from the accepted identity projection: the extraction binding
contains an input revision, which must not replace that identity. The connected
family/evidence regression detected this distinction and passes after correction.

Seal combines endpoint/predicate/qualifier witnesses per view and moves selected
observation identity validation outside the member expansion. Existing corrupt
membership, missing coverage, wrong endpoint/qualifier, duplicate assignment and
selected-identity specifications remain mandatory; query consolidation does not
relax their contract.

Latest isolated persistent target fixture (56,700 physical observations / 21,620
groups), `/usr/bin/time -l` plus the existing scale owner: native reads **27.043s**
and semantic reduction **4.169s**, both included in read/sort/reduce/final import
**42.759s**; seal **33.166s**; completed lookup **0.001044s**. Build+seal is
**75.925s**. The unchanged seal <5s gate **failed**. Whole test 92.17s; process
92.81s real, 86.03s user, 6.04s system; maximum RSS **849,821,696 bytes**. This
includes native storage/import memory and fixture creation; it is not a hard
memory-bound proof. Raw evidence: `/tmp/fact-single-stream-scale.log`.

An earlier run of the single-stream/traversal changes, before the latest seal
query consolidation and representation correction, recorded build 95.781s,
native read 60.911s, reducer 10.095s, seal 35.272s and lookup 0.000317s
(`/tmp/fact-scale-current.log`). Neither run is a controlled A/B benchmark;
do not infer a stable speedup ratio from their difference. Single-import
implementation is verified; overall first-build performance remains unaccepted.
Connected source checks across index/direct decisions, projection, canonical
publication, native pipeline/support residency and publication records: **118
distinct tests passed** across focused selections. Cancellation and oversize
stream checks are included. `git diff --check` passed. These are supporting
owner checks, not product acceptance.
No real-data migration, App build, product Case or change-verification was run.

### 2026-11-09 measured read/seal investigation on the existing target fixture

Reused the isolated persistent pytest-4050 scale store; did not recreate the
fixture, run models or touch user data. These diagnostic runs have warm storage
and are not a cold/hot acceptance benchmark. No production source was changed.

Sealing reproduced at **32.049s**. All 27 SPARQL calls were timed through full
result consumption, with wall and process CPU recorded. Member endpoint,
predicate and qualifier checks took **5.920s + 5.928s** across the two views;
current-publication membership checks took **4.026s + 1.778s**; required scalar
uniqueness took **2.882s**. The first two categories account for approximately
55% of sealing. They traverse the same physical references separately for the
assertion and relation decisions; one query per check does not mean one pass
overall. This measures query costs, not native index probes or rows scanned.

An interleaved query-shape experiment on the same store compared correlated
`FILTER NOT EXISTS` membership checks with `MINUS`: assertion **2.013s ->
0.513s**, relation **1.805s -> 0.797s**, all returning false (no violation).
This supports investigating a set-based anti-join; it does not prove malformed
input equivalence. Explicit-predicate UNION for scalar uniqueness and moving
mandatory joins before OPTIONAL did not show useful improvement. Do not adopt
those rewrites on an assumed optimizer benefit. Splitting the combined member
query into separate predicate/endpoint/qualifier queries also added repeated
scope work, rather than establishing a faster seal.

Full production input traversal, without reduction/import, took **25.469s**.
Native query preparation and result iteration account for approximately
**10.68s**. The byte-budget SUM and subsequent ORDER BY repeat the same joined
scope before consumption. A canonical entity with no outgoing observations
still spent **1.738s + 1.762s** on these two queries and returned no rows.
An indexed raw-source existence probe for that empty entity took **0.000471s**;
this is an unscoped emptiness diagnostic, not a replacement for publication
admission. Substituting a constant for VALUES did not remove the expensive
query behavior. Canonical entity count therefore remains an important missing
scale dimension in this two-canonical-entity fixture.

A separate full input cProfile run took **26.306s**, with **12,347,704** Python
calls. Native query execution: **9.887s** internal; projection page reads:
**14.521s** cumulative; individual projection restore: **11.310s** cumulative;
digest hashing: **0.849s** cumulative. These nested times must not be added.
The reader invoked `quads_for_pattern` **373,959** times and scalar `values`
**189,192** times. Each assertion view rereads its native target and target name,
even for repeated endpoints. The result first becomes two view dictionaries,
then `_physical_rows` selects fields and `_views` creates the views again.
These are concrete repeated-access boundaries; hashing is not the dominant
cost and its integrity check must remain.

Next corrections must address the joined preflight/order traversal, page-scoped
shared endpoint reads and a single physical projection decode, plus exact
set-based sealing over both views. Preserve per-view unique assignment,
selected membership/identity, endpoint and qualifier validation, cancellation
and completion fencing. A warm valid-fixture query experiment cannot replace
the corruption specifications or the unchanged seal <5s gate. The remaining
non-input/non-reducer portion of the earlier 42.759s build has not yet been
exclusively attributed to serialization versus native import.

Raw diagnostic evidence: `/tmp/fact-seal-current-breakdown.log`,
`/tmp/fact-seal-components.log`, `/tmp/fact-seal-antijoin.log`,
`/tmp/fact-read-query-breakdown.log`, `/tmp/fact-read-full-breakdown.log`,
`/tmp/fact-read-bind-experiment.log`, `/tmp/fact-read-optional-experiment.log`.
No tests were rerun for this documentation-only investigation; the prior 118
focused checks are unchanged evidence, not a new pass or product acceptance.

### 2026-11-09 native-versus-fork architecture correction (in progress)

Inspected fork `1da3cbbe10b60e000e5dbe13374a911cf7b73b0a` and upstream
`39cf7216d2326b012436efebf8a227e82f37dd3b`, including the restored uncommitted
performance draft. Upstream ConflictDetector detects differences in relationship
attributes grouped by relation identity; it does not implement qualified
propositions, explicit positive/negative contradiction or complete support
membership. EntityMerger merges entity properties, not these fact decisions.
Keep the necessary semantics in those existing owners; do not substitute the
upstream generic conflict method and silently discard these requirements.

Projection exists to bind product mention/evidence addresses to native records;
it is not a second extraction. However the existing fact projection also copies
predicate/qualifier fields already in native Relation. That redundancy is real
and is not justified merely by having necessary citation addresses. Removing
these persisted fields requires producer/reader/seal and stored-data migration
alignment; it is not safe to delete their writer alone. No such migration or
real-user-data mutation is performed in this change.

Ready/publication fencing is required by scene, query, report and daemon adoption
consumers. The custom repeated full validation in sealing and activation is not
an upstream requirement and remains a measured performance defect. The earlier
42.759s computation/import plus 33.166s seal is not acceptable performance.

Confirmed obsolete parallel implementation: OxigraphStore.stage_publication_facts
-> PublicationRecords.stage_facts -> _fact_triples has no production caller.
QualifiedFactIndex.reconcile_and_stage is the actual production final-decision
writer. Delete the parallel manual-plan writer, migrate scene/provenance/restart
fixtures to the production writer and keep corruption rejection tests at the
production seal. Tests asserting the obsolete manual-plan API are retired,
not retained as a test-only alternate writer. This deletion does not accelerate
production, because production never called it. Case delta: no-case for removing
an unused API and fixture consolidation; journey-library remains the existing
product build owner, with no pass criteria/baseline changes.

Additional upstream assessment: GraphBuilder.build's conflict step passes graph
entities to ConflictDetector.detect_conflicts; detect_logical_conflicts checks
incompatible entity types, and detect_temporal_conflicts checks temporal entity
properties. Their names do not establish qualified relationship reconciliation.
Upstream GraphBuilder also formats/copies relationships for GraphStore; using
that path would not itself establish zero-copy citations or atomic publication.

Implemented deletion also removes ExtractionRecords.read_fact_index_projections
and the index_only decoding branch. Their only callers were tests; production
already uses the full checked page decoder. There is now one projection decoder,
including digest, evidence ordering and cardinality validation. Page admission
and restart/oracle tests remain on that decoder. No data schema was changed.

The remaining production boundary must be distinguished from these deletions:
- A source address map is necessary for exact reader coordinates and product IDs;
  copying native predicate/qualifiers into it is redundant. Keep address mapping,
  remove duplicated semantic payload only with all readers and persisted-data
  migration aligned. Replacing a native ID with a new product ID is not evidence
  that a second semantic payload is necessary.
- Canonical support/status decisions are necessary; two final logical views do
  not justify two independent computations or repeated member restoration. The
  current draft removed intermediate durable views, but still writes a relation
  fact plan beside its decision and validates both representations.
- Atomic visibility of a complete result is necessary; repeated whole-stage
  endpoint/qualifier checks at seal and another membership audit at activation
  are not inherently necessary. Moving activation to a completion-fence check
  requires enforced immutability after sealing and the same-transaction fence;
  do not simply delete corruption checks while post-seal mutation is possible.

These are identified production design defects, not an assertion that the whole
fork pipeline is required or that removing unused APIs has fixed its latency.
No extra cache, engine, storage backend, certificate or compatibility path added.

Validation for this consolidation: the API-removal red specification failed
against the duplicate writer before deletion. The final focused run passed
137 tests in 51.36s across native pipeline, support-copy residency, canonical
publication, extraction records, publication records, fact projection,
QualifiedFactIndex and direct-decision tests. Includes 12 production seal
corruption variants, foreign-member replacement with equal counts, qualifier
scope/polarity separation, restart and source-support preservation. Five tests
specific to the retired manual-plan writer were removed; their corruption
requirements remain exercised through the actual production owner. Predicate
normalization fixtures now correctly expect different qualifier identities to
produce separate decisions rather than feeding an invalid manually merged plan.
Raw result: `/tmp/semantica-native-owner-consolidation-final.log`.
`git diff --check` passed. No full 56,700-observation coordination/seal benchmark,
App/change-verification run, pin update or real-data migration was performed.
The isolated activation-scale specification is included in focused tests; it
must not be reported as the full coordination/seal performance gate passing.
The pre-existing uncommitted performance draft remains unqualified by this
unused-path deletion; no unrelated host changes were included.

### 2026-11-09 production owner consolidation (in progress)

The production reducer is required: upstream generic relationship conflict detection
has no equivalent qualifier, polarity and support semantics. It remains the only
semantic owner. Remove the duplicated relation plan node: the stable canonical
fact IRI itself owns its final selection and membership. Assertions retain their
separate meaning, not a duplicated RDF observation staging layer. Consumers must
read that same final node. Old derived decision layouts require an explicit offline
`reset_fact_stage` followed by recomputation; no paid result, receipt or raw fact
is copied or reset. This is a storage-contract change, not code-hash invalidation.

Projection qualifiers are authoritative in the extraction graph and must not be
stored a second time. The normalized predicate remains a necessary derived query
key: Python Unicode casefold/whitespace normalization is not equivalent to SPARQL
LCASE. Addresses and evidence IDs remain source-derived and stable. Old projection
metadata must be converted explicitly offline, in place; normal reads must refuse
obsolete layout. Seal must retain exact coverage, ownership, selected-membership,
endpoint and qualifier checks. Activation checks cannot be removed until all
mutation paths enforce sealed immutability; raw store writes currently bypass the
owner, so a completion marker alone does not prove unchanged data.

### 2026-11-09 single observation / single decision implementation and evidence

This supersedes the preceding in-progress dual-expression design. Inspected fork
revision: 1da3cbbe10b60e000e5dbe13374a911cf7b73b0a plus the existing uncommitted
native-owner consolidation. The production owners remain `_build_source`,
`ExtractionRecords`, `QualifiedFactIndex`, `ConflictDetector` / `EntityMerger`,
and `PublicationRecords`; no new engine, temporary file, database or cache added.

Implemented:
- `_build_source` creates only `facts`, not paired assertion/relation DTO arrays.
  Source projection consumes each fact once and retains existing public IDs.
- The native projection page returns one physical observation. Coordination feeds
  it once into the existing qualifier/polarity reducer; graph DTOs are not built
  or independently coordinated. Duplicate public observation IDs are rejected.
- One final decision, at its existing graph fact address, owns one `member` set
  and count. A second assertion decision and `qualifiedMember` adjacency are gone.
  Scalar assertion ID/field selection preserve its public expression; they do not
  constitute a second body or support collection. Independent representative
  observation choices and existing status semantics remain intact.
- Assertion and graph pages read the same completed decision, without invoking
  the reducer. Generic literal assertion semantics remain in the semantic owner;
  literal objects are not converted into graph endpoints.
- Seal still rejects foreign members, substituted members with equal counts,
  duplicate ownership, changed endpoints/qualifiers/selected IDs and incomplete
  coverage. Completion is written only after the final data flush.

Replaced source consumers, fixture helper and lifecycle probes together. The
fixture helper reconstructs public expressions for semantic oracles only; this
is not a production compatibility path. Lifecycle regression observes the first
build at actual native coordination/organization boundaries, then forbids source
construction on the unchanged second build. Public semantics and paid call log
must remain identical. Old `native-final-decisions` indices explicitly fail
normal reads until offline `reset_fact_stage` and recomputation. This resets
only derived decisions, not accepted observations, original materials, receipts
or vectors. No real-data reset/migration has been executed.

Validation:
- Expanded owner/consumer selection: 238 passed, 1 failed in 68.05s. Log:
  `/tmp/single-fact-complete-tests.log`. The failing pre-existing identity test
  expects `merge_entity_group`, while the contextual resolver uses its existing
  `_merge_adjudicated_group`; neither resolver entry is changed by this delivery.
  It is recorded as a failure, not a pass or skipped acceptance.
- Includes single reducer visit, one physical decision/member set, inverted
  public representative IDs, typed facts, source references, corruption refusal,
  offline layout reset and lifecycle/reuse specifications.
- Persistent 56,700 observations / 21,620 groups: native reads 26.417s, semantic
  reduction 2.399s, read/sort/reduce/commit 45.032s, exact seal 17.269s, completed
  lookup 0.000392s. Log: `/tmp/single-fact-final-scale.log`. The unchanged seal
  budget of 5s FAILED. Removing duplicate storage is implemented; whole-build
  performance is still unqualified. These timings are not an App benchmark.
- `git diff --check` passed. Case `journey-library`: keep owner and pass criteria;
  these are supporting regression changes, no baseline promotion. App primary
  Case and change-verification were not run; no artifact/pin/installed App update.

Upstream merge assessment: this touches the fork's source-address and durable
publication owners; upstream generic conflicts are not a replacement for these
qualified-fact semantics. Preserve upstream public APIs while resolving future
merges; do not restore dual persistence or an alternative reducer.

### 2026-11-09 measured remaining cost (diagnosis only)

Re-ran the isolated persistent scale fixture with cProfile around build and seal
separately. Fixture creation (26.013s) is outside both measurements. Profiles:
`/tmp/single-fact-build.prof`, `/tmp/single-fact-seal.prof`; text output:
`/tmp/single-fact-profile-current.log`. Profiling adds overhead: build 52.885s,
seal 22.863s; these do not replace the unprofiled 45.032s / 17.269s above.
Cumulative timings below overlap and must not be added.

- Build makes 1,267,740 `quads_for_pattern` calls and 37.73 million Python calls.
  Native row production takes 34.403s cumulative; projection pages 24.746s,
  including projection reconstruction 19.461s. The 443-page interface still
  performs per-observation point reads internally, rather than a bulk field read.
- Sorting reads predicate, endpoint membership and four qualifier fields, then
  projection restoration reads ownership/endpoints/qualifiers again. The latter
  invokes `fact_qualifiers` 56,700 times (5.241s cumulative). Projection restoration
  also enumerates and hashes evidence triples and reads target display names.
- Semantic reduction is 5.995s cumulative under profiling, versus 2.399s in the
  preceding unprofiled measurement. This is not the dominant pipeline cost.
- There is already exactly ONE build `bulk_load` call. Its 51.224s cumulative
  time includes consuming the Python generator (46.874s in stream `readinto`);
  native-call self time is 4.350s. Calling this a 51-second disk import is false.
  Final output is approximately 546,000 triples; partition registration still
  makes 21,620 individual `Store.add` calls (1.110s self, secondary cost).
- Seal makes 256,623 point reads and 14.15 million Python calls. Its `fields`
  helper runs 135,020 times (21,620 decisions plus two reads per 56,700 members),
  reconstructing approximately 1.65 million fields. This loop takes 16.061s
  cumulative / 12.848s self, including iteration, RDF object conversion, byte
  measurement and dictionary construction; no isolated attribution to string
  conversion alone is established. Four SPARQL calls take 1.517s self. The main
  seal bottleneck is Python reconstruction, not these four queries or flush.

The remaining design error is repeated fine-grained native restoration across
sort, observation decode and seal, despite one final decision/member set. Next
implementation must acquire required native fields once for computation and
preserve exact ownership/endpoint/qualifier/coverage proofs without restoring all
native and projection fields again in Python. It must not merely drop corruption
checks: direct raw store writes still bypass owner immutability. No claimed
speedup is attached to that proposed change.

This fixture uses one operation, two canonical endpoints and synthetic temporal
groups; it measures production storage paths, not real ESG diversity or the App.
No production source or real data changed during this diagnostic run. The
temporary fixture was removed on completion; RSS recorded across fixture and
profiling is not a per-stage bounded-memory proof.

## 2026-11-09 correction: remove independent fact-stage seal audit

Inspected upstream/main `39cf7216d2326b012436efebf8a227e82f37dd3b`.
Upstream `TripletStore._validate_triplet` checks nonempty subject/predicate/object
and confidence bounds; it has no publication or qualified-fact sealing owner.
Consequently the full post-coordination seal was fork-added work, not upstream
reuse. Its repeated reconstruction/SPARQL auditing was an incorrect boundary.
Upstream's basic validation alone does not prove qualified-fact support coverage.

Implemented in place: physically delete `PublicationRecords.seal_fact_stage` and
its builder/test callers. `QualifiedFactIndex.reconcile_and_stage(input_key=...)`
is the controlled completion owner: point-read completed identity first, validate
admitted input count, validate exact per-group decision/member coverage before
emitting final references, import, check input fence and flush, then promote group
signatures and commit completion metadata with a final flush. Failed traversal or
partial import has no completion marker; retry can reuse only committed groups.
No temporary intermediate store, alternative reducer or compatibility reader is
introduced. ConflictDetector remains the semantic reducer. Ordinary completed
reuse performs neither native observation traversal nor reduction/import.

Validation: affected consumer selection initially 140 passed / 2 failed; both
failures were repaired (withdrawal fixture used a guessed source address and a
string instead of integer operation count; read instrumentation watched a removed
DTO restoration API). Their focused reruns passed. Final direct decision,
qualified index and canonical publication selection: 46 passed in 22.43s,
including an added omitted-input traversal regression. Coverage defects, foreign
or duplicate members, partial import/restart and unchanged-result reuse remain
covered. The initial 140 successes and focused reruns are not a single full-suite
pass or product acceptance.

Persistent synthetic fixture: 56,700 observations / 21,620 groups. Integrated
read/sort/reduce/import/completion 34.900s; native input iterator 17.866s; semantic
reducer 4.545s (nested components, not additive total); final completion mutation
plus following flush 0.183s; completed-status lookup 0.0101s. Scale test passed
in 52.94s including fixture/setup/cleanup. The former standalone seal phase no
longer exists. Completion remains under the existing 5s gate, but this is NOT a
claim that a full build or activation meets that budget. Overall first-build
performance is still unresolved. This fixture has two canonical endpoints and
synthetic temporal groups; it is not proof of general topology/RSS bounds.

Remaining limitation: `PublicationRecords.activate()` still performs separate
publication/member/coverage checks; this change does not claim their removal.
Raw database tampering after controlled completion is not audited by a deleted
seal API. Activation checks and explicit integrity auditing are distinct from
ordinary completed-result reuse. No real-user data migration, model call, App
package/pin change, journey-library or change-verification run was performed.
Case journey-library: keep existing criteria; these are supporting owner tests,
not user acceptance. No baseline or performance pass criterion was relaxed.

### 2026-11-09 worker Pillow constraint alignment

Native owner: pyproject.toml and .github/requirements/semantic-worker-*.lock, consumed by semantic_worker_release.py. Upstream core already requires Pillow>=13.0.0; six worker constraints still pinned 12.3.0 and made make dev unsatisfiable. Align all CPU/CUDA/DirectML worker constraints to 13.0.0; preserve the core security floor. Verify the macOS arm64 dependency resolution and relocated bundle through make dev; other platforms are not executed locally.

Resolution also requires docling-core 2.104.0 (first selected Pillow 13 compatible core) and its doclang 0.8.1 dependency, updated in all six constraints. Public pinned docling-slim 2.141.0 still caps Pillow<13; make dev explicitly uses the canonical local Docling wheel, whose current contract allows Pillow<14. Public release resolution remains blocked until that Docling artifact is published and pinned. No dependency bypass is added.
