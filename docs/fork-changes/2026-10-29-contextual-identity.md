# Grounded entity identity and processing cache boundary

- Record ID: 2026-10-29-contextual-identity
- Date: 2026-10-29
- Status: verified-in-stated-scope (deterministic admission; semantic recall incomplete)
- Fork base revision: ed2af3a561122827a9315343dcd8496175628df2
- Upstream reference: local upstream/main 0a2731c82 (previous diagnostic)
- Related record: 2026-10-29-reading-report-scope.md

## Reason and scope

Project identity previously treated fuzzy/exact name similarity as identity.
Corrupted canonical aliases must not seed a rebuild. Paid raw extraction and
source bytes remain reusable; identity, facts and organization must be recomputed.

## Native capability assessment

Inspected EntityResolver.resolve_entities/_detect_duplicate_groups,
DuplicateDetector._create_duplicate_candidate/is_group_compatible,
SimilarityCalculator.identity_evidence and EntityDisambiguator.disambiguate.
The last is a placeholder returning 0.8 regardless of context. Repair that native
owner, delegate from the shared detector, preserve legacy strategies for callers.
The artifact builder only binds source-grounded context and projects native results.
No host identity algorithm, whole-graph model call or second decision owner.

## Approach and actual changes

Planned: contextual candidate retrieval, same/different/unknown native decisions,
all-member group checks, explicit context/description fields, versioned project
stage cache keys and lineage. Raw mentions are the sole identity inputs.

## Verification and limitations

Regression specification: tests/kg/test_contextual_identity.py. Results pending.
Deterministic evidence cannot resolve arbitrary semantic paraphrases; unsupported
cases must remain unknown, never guessed from generic similarity.

## Upstream merge assessment

Pending incoming upstream review. Reassess the same native owners, retain a single
decision path, rerun identity, projection and project-stage regressions.

## Dated follow-ups

### 2026-10-29 — labelled variant and conflict propagation follow-up (in progress)

Inspected main HEAD d0f7088490bca5b782d16549b3b00e45d97925b3. Existing dirty
changes are preserved. Native owners remain EntityDisambiguator.prepare/compare,
DuplicateDetector._build_duplicate_groups/is_group_compatible and EntityMerger.
The existing disambiguator has no implemented LLM decision capability; do not
add a parallel prompt or silently claim semantic inference. Audit all 135 real
TCFD-related mentions before accepting the 110-member component. Add regressions
for grounded spelling variants, object boundaries and conflict bridges; retain
supported subsets and unknown results without arbitrary assignments. Replay raw
mentions offline, preserve prior evidence, and distinguish labelled identity
results from actual Summary generation acceptance. No publication or production
data replacement is included in this follow-up.

### 2026-10-29 — implemented deterministic identity admission

The planned text above records the original scope. Implementation now repairs
`normalize/entity_normalizer.py::EntityDisambiguator`, delegates contextual
candidate decisions and group compatibility from
`deduplication/duplicate_detector.py::DuplicateDetector`, and materializes those
groups in `kg/entity_resolver.py::EntityResolver`. The native artifact builder is
the caller; OntoScience does not implement a second identity decision path.

- Names, aliases and initialisms retrieve candidates, rather than authorize merges.
  Trusted scoped identifiers, located occurrence evidence, grounded descriptions
  and explicit abbreviation definitions supply the implemented positive rules.
  Conflicts veto a merge; unsupported pairs remain unknown.
- `semantic_artifact_schema.py` carries description/context. The builder admits
  verbatim source descriptions and bounded located context, preserves member
  evidence and remaps references through native resolution.
- Processed project caches bind `grounded-contextual-identity-v1`; artifact
  lineage is v4. Incremental append rejects incompatible processing lineage.
  Raw paid extraction caches remain reusable. Old canonical aliases are not
  resolution inputs. Host freshness/read paths reject missing/v3 lineage.
- No new dependency, model call, whole-graph model payload or network access is
  introduced by identity resolution. No production data was rebuilt or deleted.

Corrections made during verification: equal surrounding context is not identity;
two homonyms can occur in one sentence. Context evidence is excluded from located
mention identity. Name grounding uses word boundaries (`US` is not grounded by
`Using`). Description-based admission requires one occurrence of the name in
each context. Legacy confidence 0.8 without evidence was replaced by unknown/0.

Verification: 176 tests passed in 23.14s using `python -m pytest -q` over
`tests/kg/test_contextual_identity.py`, `tests/test_project_identity.py`,
`tests/test_project_stages.py`, `tests/kg/test_entity_resolver_exact.py`,
`tests/deduplication/test_native_resolution_veto.py`,
`tests/deduplication/test_identity_constraints.py`,
`tests/deduplication/test_cluster_merge_coverage.py`,
`tests/test_native_snapshot_append.py`, `tests/test_semantic_artifact.py`, and
`tests/normalize/test_entity_normalizer.py`. The two latest added regression
specifications failed before their source fixes. Host guard/typecheck passed;
126 focused host tests passed. Local replay and run receipts are held in the
consumer's ignored `.tmp/snapshot-audit/` directory, not in this repository.

Offline real-input replay retained every one of 36,082 raw mentions exactly once,
produced 35,887 entities (195 merged mentions), and did not combine TriStar,
TCFD, TNFD or Home Depot. This is a regression check, not semantic-quality
acceptance: 86 TCFD mentions remained 86 entities. No labelled recall/precision
score is available. Conservative fragmentation remains material.

Unimplemented: calibrated semantic paraphrase/entity linking, durable decision
provenance, and full rebuilt Summary quality acceptance. Equal generic
descriptions are not necessarily unique identifiers; description grounding does
not by itself prove referent identity. The four-word description rule is weak
for unspaced languages. Candidate buckets can still be quadratic; the existing
whole-component veto may discard valid subgroups. These limits must not be
reported as a complete disambiguation solution or accepted runtime migration.

Upstream disposition remains pending: no new incoming revision was reviewed.
The earlier local upstream reference is historical, not a claim about current
upstream. Compare the native owners above before any merge and rerun the listed
regressions and consumer migration checks.

### 2026-10-29 — scoped name reuse without mandatory mention descriptions

This correction supersedes the overly conservative admission rules and v1/v4
versions recorded above. Inspected fork HEAD was
`5776e73bc1eb71050e7e0538e190d550a1656c5a`; existing unrelated local changes were
preserved. The native owners remain EntityDisambiguator, DuplicateDetector,
EntityMerger and the artifact builder; there is no parallel host resolver.

- A grounded identical name is positive identity evidence for named entity
  types within one document representation revision. Missing descriptions do
  not veto reuse. Common person names and generic concepts remain ambiguous
  without additional support. Different documents do not inherit this default.
- Explicit full-name/uppercase-short-form definitions are indexed once per
  resolution invocation and reused throughout their representation scope.
  Competing expansions, incompatible types and conflicting trusted identifiers
  prevent automatic merging. Definitions are reset between invocations.
- Repeated occurrences of a name in one context do not themselves prove
  ambiguity. Conversely, equal generic descriptions do not identify entities
  across scopes. Different names still require actual definition/ID evidence.
- A grounded description from a supporting member survives projection even
  when the representative lacks one. The merged entity retains the description,
  its supporting mention and evidence IDs. Raw mention objects remain unchanged;
  no description is fabricated or required on every mention.
- Processed-stage version is now `scoped-contextual-identity-v2`; artifact
  lineage is `semantica-semantic-artifact-v5`. OntoScience rejects missing/v3/v4
  lineage. Raw paid extraction cache keys are unchanged and remain reusable;
  polluted canonical aliases are not rebuild inputs.

Latest verification: the same ten-file fork selection listed above passed
186 tests in 16.54s. Five focused host files passed 162 tests in 27.86s. Host
whole-repository typecheck exited 0. Both repositories passed `git diff --check`.

Offline replay rebuilt identity inputs from source-grounded raw mentions:
36,082/36,082 mentions retained exactly once, 24,503 entities, 11,579 merged
mentions, 71.511s identity processing, no network calls, maximum three aliases.
TriStar, TCFD, TNFD and Home Depot never merged with one another. Tracked groups:
TriStar one entity/one member; TNFD one entity/three members; Home Depot one
entity/12 members; TCFD-related groups 34 entities/113 members. The last includes
full-name members and must not be presented as 113 exact-name TCFD mentions.
Document/type boundaries still fragment TCFD; this is not a labelled precision
or recall benchmark and does not prove complete semantic disambiguation.

Host root guard failed on three missing ignored Explore screenshots referenced
by an existing document. Auto Test change-verification stopped before execution
because change-impact paths are unmapped. The Summary Case retains its existing
primary-owner gap and unchanged criteria/baseline. Neither is a passing gate.
Evidence is held in the consumer's ignored `.tmp/snapshot-audit/scoped-identity-*`
logs. This correction has not been packaged, deployed, committed, pushed or
published as an immutable dependency. Production graph/adoption and actual
Summary content acceptance remain unverified. Arbitrary prose disambiguation,
cross-document profile linking, quadratic candidate buckets and whole-component
veto limitations remain; no new model call was introduced to conceal those gaps.

### 2026-10-29 — project identity and separately grounded descriptions

This correction supersedes the document-boundary policy and v2/v5 versions
above. It extends the same native owners, without a host-side identity resolver
or an additional model request for identity resolution.

- Document representation scope is provenance, not an identity boundary.
  Located identical names for named entity types may link across documents;
  missing descriptions are not negative evidence. Generic concepts and common
  person names still require stronger support. Conflicting trusted identifiers,
  incompatible types, and competing acronym definitions remain vetoes.
- Definition indexes are prepared once per invocation and reset between runs.
  A unique project definition can support another document's abbreviation;
  local definitions take precedence. Whitespace, case and supported Unicode
  hyphen variants are normalized. ORG/CONCEPT extraction noise can be tolerated
  when an actual grounded definition identifies the referent. An acronym guess
  by itself is still only a candidate-retrieval key.
- The existing extraction request now has a separate optional identity_profile:
  a bounded description, an exact supporting quote, and its occurrence. The
  description may paraphrase; it is not an ontology attribute and is requested
  on defining mentions rather than every repeated mention. No per-mention
  description call or whole-graph model request was added.
- Extraction validates the exact quote and the selected mention's inclusion;
  invalid quote support drops the profile while retaining the mention and a
  rejection receipt. Window assembly translates support offsets to source
  coordinates. Artifact construction revalidates them, creates a separate
  evidence span, and retains a profile arriving from a later overlapping window.
  The merger preserves supported descriptions and their mention/evidence IDs.
  These checks prove location/reference integrity, not semantic entailment of
  arbitrary generated descriptions. Malformed profile schemas can still fail
  entity validation; provider strict schemas are the expected boundary.
- Processed-stage version is project-contextual-identity-v3; project artifact
  lineage is semantica-semantic-artifact-v6. The consumer rejects older lineage.
  Extraction-window and provider cache scopes include
  grounded-identity-profile-v1. Old completed work without matching new-contract
  extraction fails with COMPLETED_WORK_RECOVERY_GAP instead of silently buying
  new extraction. Existing paid cache bytes remain; deterministic replay may
  reuse raw mentions but cannot manufacture the missing profiles.

Source was changed in the canonical fork checkout; it is not a runtime input.
Immutable artifact publication, consumer dependency pinning, packaged rebuild,
production graph adoption and actual regenerated Summary acceptance are separate
delivery steps and have not been performed for this correction. Arbitrary prose
disambiguation, candidate-bucket cost and the whole-component veto remain known
limits; fewer entities alone is not a precision/recall acceptance result.

Final twelve-file fork regression selection passed 271 tests in 151.06s,
covering native identity/resolution/merging, source projection, processing-stage
reuse, strict extraction contracts and completed checkpoint recovery. Two
earlier failures were missing fitz in the test venv; after installing the
optional PDF test dependency, both passed in the full selection. No dependency
manifest or lockfile was changed. Host five-file regression selection passed
162 tests in 42.50s; root typecheck exited 0. Guard remains failed on the three
unrelated absent Explore screenshot references, and Auto Test selection remains
blocked by unmapped change-impact paths. The Summary Case still has its existing
primary-owner gap; neither guard nor product acceptance is reported as passed.

Final offline replay exited 0: 36,082 original mentions retained exactly once,
21,994 entities (14,088 merged mentions), 264.382s identity processing after
96.308s source grounding, zero network calls, at most five aliases. TriStar,
TCFD, TNFD and Home Depot never crossmerged. Tracked canonical groups/member
counts: TriStar 1/1, TNFD 1/3, Home Depot 1/12, TCFD-related 19/128, largest
TCFD-related group 107. The 128 includes full-name members, not 128 exact TCFD
mentions. Previous scoped replay was 24,503 entities and 34 TCFD-related groups.
This is a deterministic real-input regression, not a labelled quality benchmark;
old raw extraction lacks the new profiles and cannot validate model-generated
descriptions. Whole-component veto warnings remain in the replay log. Full
semantic disambiguation and regenerated Summary quality are not established.
Both repositories passed final git diff --check. Consumer evidence:
.tmp/snapshot-audit/project-contextual-identity-verification-20261029.md.

## 2026-10-29 follow-up: local definition evidence precedence (stage one)

Native owner remains `EntityDisambiguator.prepare/_referent/compare` in
`semantica/normalize/entity_normalizer.py`; callers remain native
`DuplicateDetector` contextual candidate generation and whole-group validation,
`EntityResolver(strategy="contextual")`, and `_resolve_native_entities` in the
artifact builder. Initial inspected fork revision was
`5776e73bc1eb71050e7e0538e190d550a1656c5a`; the shared checkout subsequently
advanced to `d0f7088490bca5b782d16549b3b00e45d97925b3` during this work. Existing
uncommitted changes were preserved. This stage repairs the native owner rather
than adding another resolver or model call.

The 19-group TCFD audit showed that competing document/project definitions were
returned before checking stronger local evidence. Two regressions failed before
the source fix (local binding despite competing definitions, and shared located
occurrence); a separate bounded-window regression also failed before its fix.
Two additional counterexamples exposed a foreign local binding being ignored
and a repeated acronym being incorrectly treated as a located definition.

Preparation now resolves an indexed full-name/acronym definition inside each
short mention's own context, including different bounded windows and case
formatting. A single located local binding overrides document/project ambiguity.
Multiple acronym occurrences in that window do not establish which one belongs
to the definition. Multiple competing local expansions remain unresolved.
Shared exact mention evidence is checked before corpus ambiguity; context and
description evidence remain excluded. Trusted identifier conflicts and
incompatible types remain higher-priority vetoes. Unqualified ambiguous acronyms
still do not merge. Definition indexes reset every resolution run.

Processing version is now `project-contextual-identity-v4`; v3 is added to the
legacy-stage rejection regression so old identity/reconciliation/organization
results cannot seed this policy. Raw extraction cache keys and artifact schema
lineage remain unchanged. No fuzzy similarity, arbitrary punctuation/word
boundary removal, project-specific acronym table or new LLM path was added.
Spelling variants and organization/framework/report object interpretation remain
outside this deterministic evidence-precedence correction.

Validation: thirteen-file native selection passed 296 tests (8 warnings,
128.93s). After adding one literal TCFD case-formatting test, contextual identity
and project-stage selections passed 49 tests (22.84s). The thirteen-file suite
was not rerun after that test-only addition. Red histories were 2 failed/28
passed, 1 failed/30 passed, and 2 failed/31 passed before their respective fixes.

Full original-mention offline replay exited 0: 36,082 mentions retained exactly
once, 21,941 entities (previous 21,994), 14,141 merged mentions, zero network
calls, grounding 181.169s and native resolution 240.377s. TCFD-related groups
changed 19 -> 15, with 128 prior members retained and seven existing full-name
mentions newly included (135 total). All 86 exact-name TCFD mentions remain.
No previous TCFD group split. Sizes are 110/7/5/2 and eleven singletons.

Old audit G3/G13/G19 join G1, G6 joins G2. Old G11 joins its literal
Climaterelated full-name group; G17 joins its literal for-expansion. Six isolated
acronym mentions therefore gain a locally defined referent; two full-name groups
newly enter the exact TCFD-related selection, explaining the net count change of
four. Spelling variants remain separate. Source contexts and full membership
comparison are in the consumer's ignored
`.tmp/snapshot-audit/tcfd-local-binding-stage1-data.json`.

TriStar remains 1 group/1 mention, TNFD 1/3 and Home Depot 1/12, with no tracked
cross-name canonical/alias merge. Remaining old G4/G5/G7/G8/G9/G10/G12/G14/G15/
G16/G18 are unresolved; preserving them and the prior large group does not prove
their object semantics correct. Native whole-component veto warnings remain.

Host root typecheck exited 0. Guard exited 1 on three unrelated missing Explore
screenshots; change-verification is blocked by existing unmapped dirty host
paths. Summary Case capability-knowledge-summary remains gap with null primary
owner; delta keep, hard gate unmet, no baseline promotion. Native regressions
and replay are supporting evidence, not Summary product acceptance. Detailed
evidence: consumer `.tmp/snapshot-audit/local-binding-stage1-verification-20261029.md`.

Upstream merge assessment: pending; no new upstream revision was evaluated.
Publication, host dependency adoption and regenerated Summary acceptance are
separate steps, not implied by fork tests or offline replay.

## 2026-10-29 follow-up: grounded separator variants and supported groups (stage two)

This completes the deterministic follow-up recorded as in progress above, not
general semantic disambiguation. Inspected revision remains
`d0f7088490bca5b782d16549b3b00e45d97925b3`; unrelated dirty work is preserved.
The native owners are `EntityDisambiguator.prepare/_definitions/_referent`,
`DuplicateDetector._build_duplicate_groups/is_group_compatible`, and the existing
artifact builder caller. No host resolver or new LLM path is introduced.

Implemented:

- Independently source-defined long expansions sharing an abbreviation can reuse
  space/hyphen variants when their compact spellings match. The rule requires
  at least four words in each expansion. Compact spelling alone is not identity;
  different words such as "for" and "on" are not erased.
- Connected positive native identity evidence can support unknown endpoint
  comparisons. An explicit different decision still vetoes the whole group.
- A direct ambiguous bridge between conflicting identities is left unresolved;
  valid supported subgroups survive. Indirect conflicting chains without a
  direct ambiguous bridge remain unmerged, rather than arbitrarily assigned.
- An unlocated short form in context containing multiple occurrences cannot
  supply abbreviation-definition evidence for either occurrence.
- Processed stage version is `project-contextual-identity-v5`; the legacy-stage
  rejection regression now includes v4. Paid raw extraction caches and artifact
  lineage are unchanged. Existing grounded entity description propagation is
  retained; no description was fabricated for legacy mentions.

Six regressions cover grounded separator variants and reverse input order,
unsupported compact names, distinct words sharing an abbreviation, supported
chains with unknown endpoints, preserved conflicting subgroups in reverse input
order, and a full report object versus an organization-name modifier. Before
the fixes the selection was 3 failed / 3 passed. A subsequent existing bridge
regression failed (1 failed / 77 passed); the occurrence guard repaired it.

Final twelve-file native regression selection: **290 passed in 9.10s**, exit 0.
Owners: contextual identity, project identity/stages, exact resolver, native veto,
identity constraints, cluster coverage, semantic artifact, normalizer, grounded
extraction/wire contracts and kernel owner regressions. No retired snapshot test
was restored. Final change after this run was a limitation comment only.

Offline replay exited 0 using all 36,082 original raw mentions, re-grounded from
source documents without old canonical aliases. All mentions occur exactly once;
native remap and registry cardinalities match. Result: **21,765 entities**,
14,317 merged mentions, zero network calls, grounding 26.063s and native identity
84.336s. TCFD retains the same 135 mentions across **11 groups** (previous 15):
124 / 2 / nine singletons. The prior 110, five-member Taskforce and seven-member
Climaterelated groups join; two former singletons also join. The two-member
"for" expansion stays separate. TriStar 1/1, TNFD 1/3, Home Depot 1/12; none
cross-merge with one another or TCFD.

All 135 TCFD contexts now have persisted usage annotations in the consumer's
ignored audit directory. They distinguish organization attribution, guidance,
framework alignment, report/index/section modifiers, table labels and unlocated
multiple occurrences. A seven-mention explicitly grounded variant subset passes
its must-link assertion. Conservative "for"/"on" separation is policy evidence,
not a gold assertion that these are different real objects. No global precision
or recall is claimed. The 124-member group is **not** semantically accepted;
legacy spans/types do not establish all organization/framework/report meanings.

Read-only audit of the consumer's old persisted Summary finds 13 reports,
291 sections, 610 temporary e-number markers, title/body entity mismatches,
mixed unrelated topic titles, and 16 identical internal-conflict template pages.
Evidence IDs resolve structurally, which does not establish entailment. This
audit did not generate new prose or validate corrected Summary output. Current
host source and old persisted projections must not be conflated.

Consumer evidence: `.tmp/snapshot-audit/contextual-identity-stage2-verification-20261029.md`,
`tcfd-stage2-data.json`, `tcfd-stage2-annotations.json`, `summary-stage2-audit.json`,
`tcfd-stage2-replay.log` and `stage2-native-tests.log`. Both repositories pass
`git diff --check`. Summary Case `capability-knowledge-summary` remains `gap`,
primary owner null, delta keep and baseline unchanged. These are supporting
checks, not product acceptance; no App rebuild/adoption, publication, commit,
push or production-data replacement occurred in this follow-up.

Remaining risks: candidate/group comparisons can be quadratic; conflicting
indirect chains stay conservative; globally overlapping definition-variant
bindings and arbitrary semantic paraphrases are not fully calibrated. No new
upstream revision was evaluated; upstream disposition remains pending.
