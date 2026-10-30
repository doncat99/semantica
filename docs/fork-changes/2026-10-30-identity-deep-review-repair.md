# Grounded identity review repairs

- Date: 2026-10-30
- Status: implemented; focused source verification passed; fresh-model and packaged acceptance incomplete
- Fork base: d0f7088490bca5b782d16549b3b00e45d97925b3 plus existing contextual worktree changes.
- Related: 2026-10-30-identity-scope-and-sense.md; consumer deep review.

## Native capability assessment

Repair EntityDisambiguator.prepare/candidate_keys/compare in normalize/entity_normalizer.py.
Actual callers are DuplicateDetector -> EntityResolver -> _resolve_native_entities.
Extraction owns grounded profiles; the artifact builder validates and locates them.
EntityMerger preserves their support. IdentityRegistryEntry is the existing persisted
identity result. No second resolver, registry, model decision path or dependency.

## Scope and verification plan

First reproduce the twelve reviewed failures through located source projection,
plus negative controls for ambiguous profile inheritance, acronyms, versions and
description negation. Repair ownership and instance boundaries, local defining
profile reuse, bounded description compatibility, candidate recall and acronym
scope. Persist unresolved candidate reasons in the existing identity result.
Keep source mentions immutable. Change extraction/processing versions when their
contracts change. No network or model calls in resolution.

Whole-corpus counts are diagnostic, not semantic accuracy. External-owner tests
support the existing host graph integrity capability; no host pass criteria or
baseline will be changed. Published dependency adoption and runtime acceptance
require the immutable artifact and remain separate from source verification.

## Upstream assessment

Pending: no incoming upstream revision examined. Overlaps normalization,
deduplication, extraction and artifact contracts. Retain only until equivalent
upstream behavior can replace it; rerun identity, grounding and cache tests.

## 2026-10-30 implementation and verification

Implemented in the existing native owners:

- `normalize/entity_normalizer.py`: open modifiers on dependent-object heads;
  grounded local ownership and owner alias reuse; owner-scoped description and
  context support; explicit report/standard instance boundaries; negation and
  order-independent literal description support; source-local acronym binding,
  quoted/noninitial abbreviations and leading-article candidate retrieval;
  broad type noise and supported local person-role reuse. A source is provenance,
  never proof that two boards share an owner. A project alias retrieves candidates
  but does not automatically bind a remote acronym.
- `semantic_extract/schemas.py` and `methods.py`: description, owner, kind and
  instance independently usable within the existing grounded profile. Owner and
  instance must occur in the supporting quote. No additional model call.
- `semantic_artifact_builder.py`: located profile validation and preservation;
  extraction contract `grounded-identity-profile-v3` and processing version
  `project-contextual-identity-v7` invalidate incompatible stage caches.
- `deduplication/entity_merger.py`: preserve owner-only profiles and grounded
  description support; original source mentions remain immutable.
- `duplicate_detector.py`, `kg/entity_resolver.py`, artifact builder/schema:
  unknown candidate reasons follow the existing identity registry, with a full
  unique candidate/reason count and sample of at most eight. References must point
  to other canonical entities. Reset per-run review state, including empty input.

Regression evidence in `tests/kg/test_identity_review_regressions.py` covers the
12 original examples, reverse-order checks, real owned-policy names, conflicting
owners/descriptions, instance bridges, scoped aliases and bounded review results.
Original audit examples first ran **22 failed / 2 passed**; additional edge
regressions went red before repair. Real replay exposed a Home Depot commitment
predicate wrongly treated as an identity definition; its regression now passes.
It also exposed local acronym-only definitions being ignored in the presence of
competing project expansions: the added regression first failed with three local
entities, and now passes. The correction reuses a source-located definition even
without a separately extracted full-name mention, without globally binding it.

Executed:

```text
.venv/bin/python -m pytest -q \
  tests/kg/test_identity_review_regressions.py tests/kg/test_contextual_identity.py \
  tests/kg/test_identity_scope_and_sense.py tests/deduplication/test_native_resolution_veto.py \
  tests/normalize/test_entity_normalizer.py tests/semantic_extract/test_grounded_llm_extraction.py \
  tests/semantic_extract/test_grounded_wire_contract.py tests/test_project_identity.py \
  tests/test_project_stages.py tests/test_semantic_artifact.py tests/test_native_grounded_source.py \
  tests/test_project_checkpoint.py tests/test_project_local_reuse.py \
  tests/test_kernel_owner_regressions.py --tb=line
```

Result: **344 passed**, eight existing PyMuPDF/SWIG deprecation warnings, 111.01s.
Two subsequently added native extraction transport cases (owner-only and
instance-only profiles with null description) also passed. They use a typed test
provider, not a real model; they do not establish extraction accuracy.
`git diff --check` passed. No host source, acceptance pass criteria or baseline
changed: `no-case` for fork-source verification only; existing host graph-integrity
acceptance remains required for immutable artifact adoption.

## Remaining acceptance boundaries

- Literal support handles reordered/subset descriptions and negation, not general
  semantic equivalence. Complementary prose and ambiguous ownership may remain
  unknown. Owner resolution supports grounded local aliases, not arbitrary
  organization identity inference.
- A no-network replay of 36,082 real mentions from 38 sources checks occurrence
  preservation and selected known bad boundaries. It is not a fully annotated
  semantic benchmark, and the old mentions have no independent identity profiles.
- Fresh-model profile quality, an independently annotated held-out sample and
  overall false-merge/false-split rates remain unverified. Local gateway probes
  failed/timed out; no fresh extraction call was sent. Synthetic typed-provider
  success must not substitute for this release gate.
- The in-memory unknown-pair collection is not bounded by the persisted sample
  size. Candidate buckets avoid unrelated all-pairs comparisons, but repeated
  ambiguous names still have quadratic worst-case work. No hard performance
  acceptance budget or memory benchmark has been established by this repair.
- No dependency publication, host pin update, production data deletion/rebuild,
  Summary generation or packaged App acceptance was performed by this repair.
  Current source results cannot certify the running App or old Summary.
- Upstream assessment remains pending: no incoming upstream revision was examined.

### Final follow-up checks

The final source review found that the prompt distinguished institutions from
frameworks but the wire enum could not express `institution`. Added that native
kind and a grounded example distinguishing an independently named Board from a
company-owned board. Its extraction regression went red before the schema fix.
The broader run after acronym-only definition repair passed **346 tests** in
110.64s (same eight existing warnings). After the institution enum addition,
the affected identity/extraction/wire suite passed **91 tests** in 1.59s.
This is transport/schema verification, not a model-quality claim.
Additional existing project source, document quality and reading-report admission
regressions passed **46 tests** in 1.78s after the final schema change.

Intermediate offline corpus replay: 38 sources, all **36,082** raw mentions preserved
exactly once, **20,612** canonical entities, **278.647s** identity phase, zero
network calls. Home Depot's 113 mentions form one group; TriStar/TCFD/TNFD/Home
Depot do not cross-mix. Selected Supplier Code of Conduct, Human Rights Policy
and Sustainability Report groups do not cross source boundaries. Unknown owner
and source referent noise still cause fragments: **20,728** mentions have review
candidates. TCFD remains 11 related groups with a largest group of 124; this run
does not certify every member's semantic referent. These are diagnostic results,
not an overall accuracy measurement. The consumer keeps the private replay inputs
and detailed evidence outside Git; no private report text is added to this record.

The intermediate replay also exposed a new acronym-context regression: a leading
article was indexed as part of a second full-name definition. Added a regression
that first failed (three entities instead of one), removed the article from this
definition path and reran identity/extraction/wire tests: **153 passed** in 1.51s.
The final corpus verification is rerun after this correction; the intermediate
entity count must not be used as a final quality result.

Final expanded source regression after the article correction: **395 passed**,
eight existing PyMuPDF/SWIG deprecation warnings, **139.14s**. This uses the command
above plus `tests/test_project_source.py`, `tests/test_project_document_quality.py`
and `tests/test_reading_report_admission.py`. No source regression was skipped due
to an observed failure; model quality and packaged adoption remain separate gates.

### Definition-boundary correction

Further review found the extracted-full-name branch still retained the leading
article when the model extracted it as part of the name. A new regression failed
with three entities instead of one; both definition branches and referent lookup
now share `_referent_name`. A second regression demonstrated that an extracted
suffix (`Standards Board` within `Sustainability Accounting Standards Board`)
created another acronym definition. The full-name branch now checks the preceding
proper-name boundary before registering that suffix. Both regressions went red
on semantic grouping before repair; the affected 155 tests passed afterwards.
This does not globally identify truncated table labels or infer acronym meaning
from background knowledge. Ambiguous short labels remain subject to review.

The completed replay immediately before these two boundary corrections yielded
20,414 entities, 20,705 mentions with unresolved candidates, and 397.263s identity
time. SASB remained severely fragmented (157 groups for 158 exact-SASB mentions).
That evidence prompted the boundary correction; it is not the final source result.
A replay started before the suffix correction was deliberately interrupted and
restarted against the final source. It is not counted as a verification pass.

Final source suite after both definition-boundary corrections: **397 passed**,
eight existing warnings, **121.77s**; focused identity/extraction/wire: **155 passed**.
`git diff --check` passed after these corrections.

The subsequent completed replay (20,392 entities, 194.905s, 20,676 mentions with
review candidates) still left 158 exact-SASB mentions in 157 groups. Further
inspection found a distinct remaining boundary error: a short expansion from
another source matched the suffix of a longer local expansion when project
definitions were retrieved into each context. A new regression failed (two local
identities instead of one). Since this lookup already requires exactly one acronym
occurrence, nested suffix matches now retain the longest grounded local definition;
the short definition in the other source remains separate. This is source-local
definition selection, not project-wide alias unification. Focused suite: 156 passed.
The preceding replay remains an intermediate diagnostic; final replay is repeated.

Final expanded regression after source-local nested-definition repair:
**398 passed**, eight existing warnings, **107.79s**. Final `git diff --check` passed.

### Completed final offline replay

Final source, 38 sources: **36,082 mentions preserved exactly once**, **20,312
entities**, **196.759s** identity phase, zero network calls. **20,672** mentions
retain unresolved candidates. Home Depot's 113 mentions share one identity;
TriStar/TCFD/TNFD/Home Depot do not cross-mix. Selected owned-policy/report groups
do not cross sources; this checks the known bad boundary, not owner accuracy.

SASB remains **109 canonical-name groups covering 159 member mentions** (some
members may be full-name mentions). No such group crosses sources. This improves
the intermediate definition-boundary regression but remains severe fragmentation,
not semantic acceptance. SEC/EPA also remain fragmented. TCFD remains 11 related
groups, largest 124: those 124 members have not been individually certified.
Do not interpret counts or source separation as overall accuracy. General semantic
equivalence, arbitrary cross-source owner identity and fresh-model extraction
quality remain open. The audit is not fully closed; full production rebuild and
Summary correctness cannot be certified by this change. No publication, consumer
pin update, model call or production mutation was performed.

### Follow-up: conservative definition variants

The remaining SASB split was traced to two native resolver boundaries. First,
`sustainability` and `sustainable` were not treated as the same conservative
inflection, and compact spacing/hyphen variants such as `Task Force` versus
`Taskforce` were not grouped. Second, the grounded full standard name was still
classified as a dependent `Board`, while a remote bare acronym was either
over-bound or rejected for the wrong reason. The resolver now groups only
independently grounded expansions that share either the conservative token
fingerprint or the exact compact spelling; singleton expansions do not become
global aliases. A remote bare acronym may reuse that binding only when multiple
raw expansions collapse to one canonical definition. Different expansions such
as `Social Accountability Standards Board (SASB)` remain unresolved.

The focused identity, contextual-scope, sense, grounded-extraction and wire
contract suites now pass **158 tests**. The offline deep review covers 12 cases,
including acronym hijacking, owner-dependent boards, report instances, article
variants, and irregular abbreviations. A repository-wide pytest collection was
not a valid gate in this checkout: 27 pre-existing collection errors require
missing integration import paths, an older parser API, or the unavailable
`semantica_mcp` package. No new corpus replay was claimed from this patch; the
last 36,082-mention replay above remains diagnostic and must be rerun before any
rebuild decision.

The broader selected source/project run completed **1,347 passed, 44 skipped, 8
failed**. The eight failures are pre-existing provider/retry test-environment
compatibility failures in `semantic_extract` (mock logging, MagicMock span
serialization, and unavailable provider/MCP behavior); none are in the 158-test
identity/disambiguation gate. They remain an explicit release gap rather than a
silently ignored pass.
