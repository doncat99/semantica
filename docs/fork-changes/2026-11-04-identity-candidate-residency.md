# Identity candidate residency red specification

- Record ID: 2026-11-04-identity-candidate-residency
- Date / author: 2026-11-04 / Codex
- Status: implemented and verified for transient candidate-object residency only
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected
- Related work: G4 native builder/global algorithm resource remediation

## Reason and native capability assessment

The current builder delegates identity decisions to
`kg/entity_resolver.py::EntityResolver.resolve_entities`, using the contextual
`deduplication/duplicate_detector.py::DuplicateDetector` owner. Its
`_contextual_candidates` retrieves by names, definitions and scoped identifiers;
this avoids unrelated pairs but still retains every merge-allowed candidate
within a repeated-name bucket. Group partition and merger compatibility checks
also inspect pairs. No alternative identity implementation is introduced.

Inspected caller: `semantic_artifact_builder.py::_resolve_native_entities`.
Existing tests include `tests/test_native_reduction_boundaries.py`; the new
dedicated regression isolates candidate object residency before later merging.

## Actual changes and desired contract

Added `tests/test_native_identity_candidate_budget.py`. Three offline corpora
contain 16, 32 and 64 independently located mentions of the same organization.
The real contextual owner decides every pair. Runtime weak-reference finalizers
measure simultaneously live `DuplicateCandidate` instances; the consumer retains
only normalized pair IDs and checks the complete combinations oracle, duplicate
emissions, and each `same` / merge-allowed decision before checking residency.

The desired complexity bound is at most one resident candidate object per input
mention while every admitted pair remains covered. It is a test of linear
transient pair-object residency, not a product admission cap or permission to
truncate candidates. The test accepts an iterable, allowing the existing owner
to stream candidates without creating a new public algorithm or API.

The native `_contextual_candidates` now yields each merge-allowed candidate
directly, in the existing order, and `_build_duplicate_groups` accepts its
iterable. No pair is dropped; decisions, review bitsets, conflict partition and
merger compatibility rules are unchanged. The only runtime caller consumes the
stream fully before partition and diagnostic use. No dependency, persisted data,
policy, model call or network behavior changed.

Streaming the first candidate stage alone does not prove that the
downstream duplicate groups, conflict graph, review bitsets or full builder are
bounded; those remain separate G4 requirements.

## Verification and limitations

- Expected red command: `.venv/bin/python -m pytest -q
  tests/test_native_identity_candidate_budget.py`.
- Current implementation retains n*(n-1)/2 simultaneous objects: 120, 496 and
  2016 for the three corpora. Full pair coverage and decisions are unchanged.
- Observed run: **3 failed in 1.17s**, all at the final peak-residency assertion.
  Complete pair coverage, pair uniqueness, every decision and zero candidate
  objects after consumption passed before each expected failure.
- After the owner change, the same command: **3 passed in 1.37s**.
- `.venv/bin/python -m pytest -q
  tests/kg/test_identity_review_regressions.py
  tests/deduplication/test_deduplication.py
  tests/deduplication/test_cluster_merge_coverage.py`: **163 passed in 3.00s**,
  including review reset, exact post-merge diagnostic counts and indirect
  conflict/compatible-subgroup preservation.
- `.venv/bin/python -m pytest -q tests/kg/test_contextual_identity.py
  tests/kg/test_identity_scope_and_sense.py tests/kg/test_entity_resolver_exact.py
  tests/deduplication/test_native_resolution_veto.py
  tests/deduplication/test_identity_constraints.py
  tests/deduplication/test_merge_selection_sources.py
  tests/test_native_identity_candidate_budget.py`: **131 passed in 1.55s**.
- Scoped `git diff --check` passed. These focused suites do not establish
  whole-repository health or a bounded full resolver/build.
- G4 remains incomplete; no immutable artifact or ESG acceptance is asserted.

## Upstream merge assessment

- Disposition: pending; incoming upstream not reviewed.
- Preserve full candidate/identity semantics during a future owner fix and
  rerun conflict-bridge, ambiguity, alias and identity provenance regressions.

## 2026-11-08: replace repeated restoration with native identity decisions

The earlier streaming fix addressed candidate-object residency only. It did not
remove repeated original-text hydration, equivalent-pair comparisons, repeated
component scans, merger re-adjudication, or downstream resolver calls. Those
boundaries are now replaced in the same current native owners:

- `EntityDisambiguator.identity_projection` extracts bounded grounded observations;
  dependent rules replay those observations instead of reopening original rows.
  The native candidate index retains only identity properties and their scopes,
  not arbitrary attributes, descriptions, source paragraphs or paid receipts.
- `DuplicateDetector` shares comparisons only across decision-equivalent
  mentions; affirmative identity alone permits merging. Unknown twins remain
  distinct, and internal vetoes survive external support bridges. Trusted identifiers, scope, shared provenance and every unary decision
  input remain part of equivalence. All original members remain in the result.
  The existing conflict partition is retained; transitive support does not erase
  conflicts. The contextual merger consumes an already adjudicated group without
  repeating its pair comparisons; arbitrary public merge inputs remain validated.
- `IdentityCandidateIndex` uses union by size/path compression, writes final
  memberships once, and stores forward cursor links. Per-component decision
  dependencies include missing keyed observations and field enumeration, so new
  definitions can invalidate decisions in other sources. Unaffected canonical
  memberships and selectors stay at their original addresses, without copying.
- `PublicationRecords` preserves only a completed identity stage across generation
  changes. Exact input identity excludes embedding, package/code digests and task
  state. Incomplete stages are discarded rather than promoted or reused.
- `semantic_publication_builder` consumes selected fields and membership references
  downstream. Topology reads only canonical IDs/names; reading completed canonical
  entities never invokes the resolver. Field metadata, including owner-only identity
  profiles and description provenance, has explicit native selectors.

The host integration distinguishes ensure-current from explicit rebuild and finds
an adopted valid result independently of a later canceled/failed attempt. No new
knowledge engine, compatibility reader, paid-result copy, model or dependency is
introduced. Derived observations and decisions remain in the current publication
owner; original extraction data and receipts remain immutable in their owner.

Verification: 285 connected identity/consumer/publication specs passed in 36.07s;
31 equivalence/index/early-cancellation specs passed in 12.24s. Native incremental
and both 5,000-mention fixtures also passed. The unknown 5,000-mention resolver and
all review summaries completed in 0.88s: one comparison, 5,000 independent entities,
4,999 alternatives counted per mention with eight samples. Positive twins likewise
share one comparison and retain every original member. Exhaustive four-class
support/unknown/conflict graphs retain the original partition oracle, including
internal unknown and contextual-veto twin classes.

Feature rows and native component DTOs have explicit byte limits; removing the
old arbitrary 4,096-member default does not assert unlimited component capacity.
Compact replay uses a temporary file; native component hydration enforces a
16 MiB reference budget and a separate 16 MiB serialized DTO budget. These are
admission limits, not measured whole-process RSS bounds. Synthetic
repetition results establish only the identity boundary, not real ESG completion,
installed-artifact qualification, or an end-to-end performance claim. This change
does not migrate or rebuild real user data. Upstream assessment remains pending;
the contextual six-pass extension belongs to this fork, not upstream Semantica.

2026-11-08 installed acceptance correction: the model-path fixture still hashed
five organization-product identity fields while the current native/host owner
requires the actual inputDigest as the sixth field. Packaged acceptance reproduced
the mismatch as `organization report product receipt identity is invalid`.
Updated the existing fixture relay to the current contract; production identity
validation remains unchanged. Rebuilt artifact installed acceptance passed:
`sha256:2849bfb02840a5800d44dd7851d0b95d860bd27479120da557fdb4e7519f2dce`
(34,737 files). This qualification does not replace real ESG product acceptance.

### 2026-11-08 real ESG dependency recording correction

The installed ESG run `5dabe95d-95fa-4f1f-b31b-e855f78731d1` failed in
`NativeIdentityContext.observe`: a complete candidate component's dependency
set exceeded the 1 MiB in-memory/single-literal representation. This was a
representation limit, not corrupt extraction or an embedding failure.

The existing native owners `NativeIdentityContext` and `IdentityCandidateIndex`
now flush at most 128 keyed dependencies / half the native atomic byte budget
per batch into the same publication graph. Each dependency is an individual
literal under its decision group. No second store, copied paid facts or raised
aggregate limit is introduced. Map-enumeration dependencies follow the same
recording path. Reconciliation streams all dependencies; the completed group
link is written only after dependencies and canonical references are staged.
An interrupted unsealed attempt cannot be reused and its rows are replaced on
retry. Callers and the contextual resolver contract are unchanged.

Regression: `test_component_dependencies_stream_beyond_single_write_budget`
first reproduced the real exception, then checks >1 MiB complete dependencies,
normal retention, and invalidation by a newly available definition. Existing
incremental/context/index tests are run with it. Real ESG completion remains
unverified until the corrected immutable package completes; earlier extraction
9.23s and vector 42.27s measurements are stage totals, not total-build success.
This modifies fork-only dependency persistence; review this owner on upstream
merges rather than introducing an alternate resolver.

### 2026-11-08 identity completion coverage correction

Native owner: `PublicationRecords.seal_identity_stage`, called by the publication
builder and delegated by `OxigraphStore`; inspected dirty `main` in the canonical
checkout. The installed real run reached 45,580 mentions / 25,286 canonical
entities, then native sampling showed the SPARQL anti-join consuming CPU. Its
coverage query joined the full canonical set for each mention. Replace that query
in place with one forward mention traversal, indexed reverse member lookup and
current-head membership point reads, with cancellation between mentions. No
facts, paid results, decisions or completion validation are removed or copied.
The focused regression rejects the old anti-join, verifies exactly one reverse
lookup per mention and rejects membership from unregistered canonical entities.
Red: 1 failed; green: coverage plus generation-reuse specs, 2 passed. Real packaged
validation remains pending; this source change is not an installed-runtime claim.
The same anti-join also existed in `activate` for canonical fact coverage; it now
streams native relation references and checks reverse membership plus current
head registration. Two added specs fail red on the previous query and pass for
both complete and missing coverage. Indexed coverage/generation specs: 4 passed;
existing identity/publication/canonical-reader specs: 67 passed in 45.64 seconds.
Synthetic in-memory Oxigraph coverage: 1,000 mentions 420.41 ms -> 9.77 ms;
4,000 mentions 7,446.58 ms -> 24.33 ms. These are query measurements, not an
end-to-end performance claim.

### 2026-11-08 restart retention lookup correction

`PublicationRecords.begin` and `reset_identity_stage` share `_identity_selection`.
The selector branch joined every registered canonical before matching each row's
subject. A real restarted worker remained inside the native DELETE/INSERT filter;
macOS native sampling confirmed SPARQL EXISTS evaluation and repeated iterator
advancement (the sample alone does not identify Python frames). Repair the shared
ownership predicate by reverse lookup of the row's selector owner, then nested
indexed registration check. Retention and deletion remain one atomic mutation;
no copied result, new cache, weaker integrity rule or alternate owner is added.
The generation/restart regression failed red on the unbounded selector join and
passes with the existing exact retained-quad and dependency assertions. Identity
candidate/publication regressions: 62 passed in 26.45s. A read-only real-store
selection retained 1,162,123 identity triples in 18,973.87ms. Actual packaged
restart and downstream adoption still require the corrected artifact to run.
Upstream merge assessment: fork-only publication ownership; preserve current
head registration semantics when merging native storage changes.

## 2026-11-08 qualified partition indexed access correction

Native owner `QualifiedFactIndex._references` and `stage_reconciled` formerly joined the full head observation set before selecting one partition/identity. Real current ESG has 56,700 observations and 21,620 partitions. A read-only exact-field query returned the same 8 records in 1046.380ms before versus 0.946ms with partition-first lookup and correlated current-head membership validation (`.tmp/identity-fact-partition-real.json` in the host workspace). This is query evidence, not whole-stage timing.

Replace both joins in place with the existing indexed partition/identity lookup plus a current-head membership point check. No new index, schema, owner, paid-result copy or semantic change. Caller remains the existing builder fact reducer and canonical page reader. Regression fails before the state-write fix and verifies orphan exclusion, seek query shape, exact qualified oracle, cancellation, withdrawal and page coverage. Related native tests: 19 passed in 5.94s. New immutable App qualification and real adoption remain pending; installed artifacts are not hot-patched.

## 2026-11-10 selected-field reads and build resource lifetime

Inspected fork main bf72221141e8ecac431778e118a8223b70d4d494. Real ESG run
40cfdf28-fcc8-4473-8fa7-9a7c02980990 failed after 151.485s: organization restored
all member summaries for a 380-member canonical entity, exceeding the existing
256 KiB budget at member 328. This was fork-owned read amplification, not native
community detection. Replace `_native_canonical_entities` in place: hydrate the
representative and actual field selectors only, verify each selected membership,
and read cited evidence through exact membership queries. Complete provenance
stays in the existing paged membership owner. Remove summary aggregation and its
production callback. Canonical fact DTO reads likewise stop enumerating support
observations; `PublicationRecords.fact_members` retains exact bounded details.
No support record, semantic decision, evidence binding or budget is removed.

Organization retains native `CommunityDetector` greedy modularity. Title names
are fetched through bounded selected-name projections after detection, instead
of a per-entity name read for the whole graph. `ExtractionRecords.from_operations`
and publication admission project receipt bindings in bounded pages and retain
logical/physical identity, completion and corruption validation. Embedding SQLite
owners live for the concurrent embedding phase and close on success or failure,
instead of reopening per range; vector integrity checks remain intact.

Affected callers: publication builder organization, canonical entity/fact readers,
source admission, embedding dispatch. Regression coverage includes large support,
selected-field/foreign-member rejection, exact paged support, semantic oracle,
withdrawal/restart, one-row receipt projection and phase connection cleanup.
Packaged and real ESG results are pending and are not implied by focused tests.
Upstream merge assessment: selected-field and publication owners are fork code;
retain upstream community semantics and vector-store locking/lifetime guarantees.

Selected-title follow-up: the first dynamic-graph bulk query regressed on the
real multi-graph store (128 names did not finish within 15 seconds). It is
removed. `PublicationRecords.canonical_names` now reads exact graph/address
indexes, checks selected membership and scalar uniqueness, and retains page and
byte bounds. A regression rejects query joins and support enumeration. The
same real page took 0.300 seconds; 9,200 title names took 2.989 seconds, within
a 20.827-second upstream community computation. These are owner measurements;
packaged ready and repeated ensure still require separate acceptance.

2026-11-10 artifact-publication follow-up (source implemented, packaging pending):
real run `5c585e8d-048d-4557-9560-7ae25d4e0e63` passed the former canonical
entity failure, completed organization in 154.325s, then failed vector publication
after about 265s of artifact work. Accepted vector ranges may include serializer
newlines before/after a scalar; extraction grounding intentionally excludes those
boundary characters. The vector address producer incorrectly reused that trimmed
proof for an exact accepted-input extent. `_embedding_native_ranges` now retains
proven boundary separators with bounded addresses; publication validates their
whitespace, placement and exact extent, and `_document_hit` reconstructs both.
Extraction proof, operation identity, paid vector rows and receipts are unchanged.
All 8,349 real accepted extents passed a read-only address check (10.663s).

`GraphSearchIndex.publish_native_positions` maintained its inverted B-tree for
every token with a 2 MiB SQLite cache and repeatedly selected the same interned
terms. Defer that index until all positions are inserted in the transaction and
use a 1 MiB bounded term-ID memo. The same lexical schema and query semantics
remain; cancellation removes an unfinished target. A real 38-source scratch
publication took 30.772s, produced 541,085,696 bytes and peaked at 121,126,912 RSS
bytes. This is not whole-build acceptance. New regressions cover exact boundary
reconstruction, rollback on extent damage and repeated-token SQL work. Both
owners are fork additions; no upstream algorithm or input-specific shortcut was
introduced. Final ready, activation budget and repeated ensure remain pending.

2026-11-10 publication write-boundary correction: real run
`3f5a3067-dfa5-4e5f-b2cd-3f2047dab640` finished native artifact writing in
789.010s, then the host rejected its partial-work receipt manifest. Sampling
found 1094/1206 main-thread samples in RocksDB flush waits during the sampled
window; this is not whole-stage attribution. Builder community/topic writes
had recreated PublicationRecords through store wrappers, bypassing its existing
checkpointed write boundary. Both callers now share one PublicationRecords and
its existing bounded checkpointed scope; no new checkpoint store or result
carrier is introduced. Production-path tests require the shared active scope.

Grounding formerly restored range bounds before establishing source admission.
It now proves the current source/operation first, ignores unrelated ranges and
retains exact record/evidence ownership and overlap checks. A red regression
places malformed ranges in another source. Real read-only sampling still took
6.592s for 128 vectors/1201 scalar positions; source-local physical access is
not yet a proven performance win. Broader SPARQL and URI-derived admission
experiments were confined to ignored host scratch and were rejected; neither
experimental implementation enters production. Native activation, packaged ready
and repeated reuse must still be measured. Upstream assessment: these are fork
publication-owner/caller defects, not upstream community detection changes.
