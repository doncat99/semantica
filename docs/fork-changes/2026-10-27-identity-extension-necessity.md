# Remove unjustified identity recall and fuzzy alias expansion

- Record ID: 2026-10-27-identity-extension-necessity
- Date / author: 2026-10-27 / Codex
- Status: verified-in-stated-scope; not released
- Fork base revision: fa7af6313242343efa6e46eacb708ea4e92a3c37
- Upstream reference: local origin/main ca6c9f1918ad05e2bbaa4922fb32f34e2a508bb9; not refreshed
- Related records: 2026-10-18-native-resolution-conflict-veto.md; 2026-10-18-native-identity-constraints.md

## Reason and scope

The consumer owner requested evaluation and physical removal of unjustified fork
behavior. Three red tests reproduced unrelated primary names promoted from 0.5914
to 0.892 through near aliases, nine fuzzy comparisons instead of one with two
aliases per entity, and identity declarations expanding native candidate recall.
The latter contradicts the existing conflict-only contract. No independent
quality evidence justifies fuzzy alias expansion.

## Native capability assessment

- Inspected owners: SimilarityCalculator scoring/blocking, AliasResolver,
  DuplicateDetector pair/component/incremental validation, EntityResolver and
  EntityMerger configuration, semantic_artifact_builder `_resolve_native_entities`,
  PipelineBuilder and ExecutionEngine.
- Callers/tests: native batch/incremental/direct merge, project identity and fact
  remapping, artifact worker/contracts, extraction and checkpoint suites.
- Decision: repair existing scorer; remove Cartesian fuzzy alias scores and
  identity positive candidate blocks. No second resolution implementation.
- Retain explicit exact aliases: native AliasResolver normalizes declared maps,
  but upstream scoring does not consume entity alias arrays. IBM and an explicitly
  declared long name need to resolve without adding inferred/fuzzy aliases.
- Retain conflict vetoes: scoped trusted conflicting identifiers must not merge
  or bridge through missing identifiers. Matching identifiers do not expand recall;
  native property scoring otherwise remains unchanged. Caller trust is required.
- Retain shared detector config to prevent divergent policies between detection
  and materialization; this does not eliminate native repeated detection.
- Retain minimal DTO/provenance/member/endpoint projection: native resolver does
  not output the consumer artifact contract; generic pipeline handlers are not
  an equivalent replacement. No independent merge decision belongs in the builder.

## Approach and actual changes

- `similarity_calculator.py`: exact normalized declared-name intersection or one
  canonical-name native fuzzy comparison; remove identity positive candidate blocks.
- `test_identity_constraints.py`: three regression-first tests, case/whitespace
  normalization, exact-alias conflict precedence; rename older misleading tests
  attributing explicit-alias recall to shared identifiers.
- Append dated corrections to earlier fork records, preserving history.
- No public DTO, dependency, network/model request, cache version or key changes.
  No fallback, feature flag, data deletion or paid-result invalidation. Existing
  wrongly merged artifacts are not automatically split by a source change.
- Project-wide references remain necessary; current all-at-once computation is
  not performance-qualified. Native first-letter pair allocation and re-detection,
  and quadratic component conflict validation remain scale risks.
- Missing downstream progress/restart reuse are real integration gaps, not
  implementations to delete. Follow-up must use existing worker progress and
  SnapshotCheckpoint owners with data/semantic-contract validity, not code hashes.
  No new progress or checkpoint subsystem is added in this assessment.

## Verification and limitations

Run with `SEMANTICA_DISABLE_PROGRESS=1 SEMANTICA_DISABLE_JUPYTER_PROGRESS=1
PYTHONDONTWRITEBYTECODE=1`, Python from sibling canonical `semantica/.venv`,
`-m pytest -q -p no:cacheprovider` in this source checkout.

- Red specifications: all 3 failed before correction.
- Final focused suite: 263 passed, 5 subtests passed, 3 existing deprecation
  warnings, 9.39s. Paths: tests/test_project_identity.py,
  tests/test_project_fact_identity.py, tests/kg/test_entity_resolver_exact.py,
  tests/deduplication, tests/kg/test_entity_pipeline.py,
  tests/kg/test_core_components.py, tests/kg/test_graph_builder_with_graph_store.py,
  tests/kg/test_graph_builder_extraction_defaults.py, tests/test_semantic_artifact.py,
  tests/test_semantic_artifact_contract.py.
- Expanded suite added tests/test_semantic_artifact_native_extraction.py,
  tests/test_project_checkpoint.py, tests/test_semantic_artifact_long_context.py:
  324 passed, 5 failed, 5 subtests passed, 67.02s before final normalization tests.
  Two lack optional fitz. Three assert one request but current strict validation
  retries three times. Loading original HEAD similarity module and rerunning the
  failing tests reproduced all five failures (1 passed, 5 failed, 9.35s).
  No unrelated tests weakened. Counts overlap and must not be added.
- Consumer guard/typecheck passed; git diff --check passed in both repos.
- No production Build, installed artifact validation, independently adjudicated
  corpus/scale benchmark, publication, pin change or migration. These are supporting
  tests, not product acceptance. Prior long local computation is not claimed fixed.

## Upstream merge assessment

- Disposition: drop fuzzy alias expansion and identity candidate blocks now;
  retain exact declared aliases, conflict veto and shared config until equivalent
  upstream capability is verified. Remove obsolete fork code when it exists.
- Incoming upstream revision: not fetched beyond the local ref above.
- Overlap: SimilarityCalculator, AliasResolver, DuplicateDetector, EntityMerger,
  EntityResolver. No parallel algorithms permitted.
- Required regressions: no-conflict native scores/candidates, alias normalization,
  conflict precedence/bridges, incremental/direct merge, shared configuration,
  member evidence preservation and relationship endpoints.

## Dated follow-ups

2026-10-27: source verification only; no release, production data change or paid call.
