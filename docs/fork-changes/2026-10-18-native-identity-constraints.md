# Preserve identity constraints in native entity resolution

- Record ID: 2026-10-18-native-identity-constraints
- Date / author: 2026-10-18 / Codex, requested by fork owner
- Status: implemented; offline verification recorded below; not released
- Fork base revision: c1fe1d203766c00186e59a19ec27050133d86c14
- Upstream reference: local origin only; no new upstream merge reviewed
- Related records: 2026-10-18-native-first-policy.md

## Reason and scope

Offline probes reproduced type-conflicting entities merging through an untyped
bridge, identifier strings receiving fuzzy similarity, and explicit aliases lost
before native detection. Existing project identity/exact tests did not cover these
semantics. Generic name deduplication is not company identity confirmation.
No new LLM path, identity.py, exact_key, ESG scorer, dependency or runtime registry.

## Native capability assessment

- SimilarityCalculator owns property/name scoring and blocked candidate generation.
- DuplicateDetector owns pair eligibility and connected duplicate groups.
- EntityMerger owns materialization/provenance; EntityResolver orchestrates them.
- AliasResolver owns configured alias normalization; artifact projection delegates.
- Inspected all callers via rg, existing deduplication tests, exact resolver tests,
  project identity tests, recent removal 959ef4e7, ontology property definitions,
  RelationalSchemaMapper and ConflictDetector. The latter compares sources of an
  already identified entity; it does not supply pre-merge identity constraints.
- No identity-property semantics contract exists in native deduplication. Extend
  the existing calculator configuration with property_schema declarations and
  optional require_identity, not a second schema registry or detector.
- Scope is supplied by declared property fields, not inferred from field names,
  company names or ESG. Unscoped declarations assert stable identity for their
  input dataset. Time-dependent facts require caller-resolved scope; the resolver
  does not infer temporal overlap or source authority.

## Approach and actual changes

Planned: regression first; native constraint checks shared by detection/grouping/
explicit merging; aliases and declared identifiers participate in existing
blocking; consistent detector/threshold through resolver and merger; preserve
aliases at artifact projection. ESG carries existing issuer context to its one
Review owner and binds it to cached decisions; no extra resolution pass.

## Verification and limitations

Pending implementation and test results. Synthetic fixtures diagnose contracts;
they are not independently adjudicated real company or delivery acceptance.
No deployment, paid calls, production start or persisted business changes.

## Upstream merge assessment

- Disposition: pending. Compare incoming native owners before retaining changes.
- Remove/adapt these extensions if upstream provides equivalent property semantics
  or constrained grouping; never preserve two competing implementations.
- Re-run generic deduplication, exact/fuzzy resolver, incremental merge, artifact
  projection and ESG Review/cache regressions after merge.

## Dated follow-ups

2026-10-18: implementation and verification pending.

### 2026-10-18 implementation follow-up

The planned entry above is retained as history. Implementation now lives only in
the existing native owners:

- SimilarityCalculator: caller-declared identity properties use exact typed scalar
  equality within complete declared scopes. Conflicts cannot be outweighed by
  names; strict mode abstains without agreement. No names/hosts/identifier fields
  are embedded in the algorithm. AliasResolver normalizes explicit aliases;
  existing blocking includes aliases and declared identifiers. Missing properties
  on both sides are neutral (0.5), not affirmative evidence (previously 1.0).
- DuplicateDetector: pair constraints also govern whole connected components,
  including type-conflict and missing-identity bridges. Incompatible components
  are excluded before max_results/top_k truncation, including incremental input.
  Existing object metadata properties survive native batch projection.
- EntityMerger: explicit group merge cannot bypass detector constraints;
  MergeStrategyManager preserves observed names/aliases after materialization.
- EntityResolver: detection and merging share one detector/configuration and
  threshold; conflicting configuration fails explicitly, including exact mode.
- Semantic artifact builder: passes existing aliases to native resolution. Its
  default remains generic deduplication, not strict issuer identity confirmation.
- New tests: tests/deduplication/test_identity_constraints.py; extended
  tests/test_project_identity.py. No new exported resolver or dependency.

ESG consumer changes (separate checkout) pass canonical company context to its
existing Review call and persist the actual context in decisions/failures/cache
bindings. They do not introduce native entity resolution as an additional Review
precondition or add an LLM call. These are not yet pinned to a released fork SHA.

Regression-first evidence: initial new tests failed before implementation. Two
additional tests reproduced greedy incremental selection and object-property
loss; another three reproduced result-cap ambiguity and batch metadata loss.
All were repaired in the owners above, without per-case exceptions. An interim
broad run passed 244 tests and 5 subtests; final expanded results follow below.

Limits: identity semantics/source trust are supplied by the caller, not inferred.
Scope matching does not implement temporal reasoning. Whole-component abstention
trades recall for safety. Compatibility checking is quadratic within generated
components; no scale benchmark was run. Existing blocking and candidate-generation
caps remain approximate: absence of a generated connection is not global proof of
distinct identity. Generic mode may still merge names without identifiers; strict
mode is opt-in. Synthetic contract tests are not real-company adjudication.
No paid models, push, deployment, production start or business-state migration.

Upstream disposition remains pending: inspect incoming native property semantics,
aliases, grouping and configuration before keeping/adapting/dropping each change.

### 2026-10-18 final native offline verification

247 passed, 5 subtests passed, 3 existing ProvenanceTracker deprecation warnings,
43.48s. Run from this fork using .venv/bin/python:

```sh
SEMANTICA_DISABLE_PROGRESS=1 SEMANTICA_DISABLE_JUPYTER_PROGRESS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_project_identity.py tests/kg/test_entity_resolver_exact.py tests/deduplication tests/kg/test_entity_pipeline.py tests/kg/test_core_components.py tests/kg/test_graph_builder_with_graph_store.py tests/kg/test_graph_builder_extraction_defaults.py tests/test_semantic_artifact.py tests/test_semantic_artifact_contract.py tests/test_semantic_artifact_native_extraction.py
```

The final implementation puts pre-cap compatibility filtering in DuplicateDetector,
shared by batch and incremental detection; EntityMerger does not contain a second
group-filter implementation. git diff --check passed. This is affected-path
regression, not a full-repository, scale, live ESG or release acceptance result.

### 2026-10-18 positive-identity admission correction

The generic artifact/default-mode description above is superseded by
[positive-identity admission](2026-10-18-positive-identity-admission.md): artifact
registration now always uses strict native admission, identity declarations default
to strict admission, and missing evidence retains its ordinary candidate similarity
while identity remains unresolved. Generic deduplication compatibility is retained
outside the authoritative artifact identity path. The follow-up records regression,
new request/registry fields, lineage/checkpoint fences and compatibility risks.

### 2026-10-18 final correction: native positive admission plus negative veto

The owner rejected mandatory identifier admission. This supersedes both the
strict opt-in design and the positive-identity admission follow-up above.
require_identity and the unshipped registry status are removed; native positive
scoring (including empty properties 1.0) and artifact name resolution are restored.
Identifier agreement no longer shortcuts to score one. Only declared comparable
conflicts veto; missing identifiers/scopes are not negative evidence. Existing
type/bridge/component/cap/incremental/explicit-merge protections remain.

See [current correction record](2026-10-18-native-resolution-conflict-veto.md) for
implementation, 297 passed / 5 subtests, checkpoint fence and upstream merge risks.
Prior entries are preserved as history, not alternative supported algorithms.
