# Separate similarity from confirmed identity

- Date / author: 2026-10-18 / Codex, authorized by fork owner
- Status: planned; regression-first results pending
- Inspected fork base: c1fe1d203766c00186e59a19ec27050133d86c14 plus local changes
- Related record: 2026-10-18-native-identity-constraints.md

## Reason and native ownership

The previous optional strict mode did not protect artifact identity registration:
the builder still used generic name deduplication. Strict scoring also represented
missing evidence as score zero, conflating uncertainty with dissimilarity.

Reuse SimilarityCalculator.identity_evidence for evidence status,
DuplicateDetector for merge admission, EntityResolver/EntityMerger for grouping
and materialization, and the existing artifact projection/registry. No second
matcher, LLM, hardcoded entity types/names/identifier fields or inferred authority.
Inspected native callers with rg, native and artifact identity tests, builder
request schema, checkpoint and worker boundaries. Existing generic dedup callers
remain supported; identity declarations default to strict admission.

## Planned change

Keep similarity available without identity confirmation. Conflicts veto;
strict identity requires positive agreement, otherwise remains unresolved.
Artifact registration uses strict native resolution, including when no trusted
identity schema is supplied (abstain, not fallback). Caller-declared property
semantics reuse the native schema; arbitrary extracted attributes are not trusted
automatically. Preserve mention IDs, evidence, aliases and relation endpoints.

## Verification

Pending. No deployment, data migration, paid model calls or release claim.

## Upstream merge assessment

Pending. Inspect incoming native evidence/admission/registry owners, adapt or drop
this change if equivalent support exists, never retain competing implementations.
Check generic dedup, strict batch/incremental/explicit merge, artifact/worker
contracts and cache/checkpoint behavior. Identity scope and source trust remain
caller responsibilities; no temporal inference or real-world adjudication proven.

## 2026-10-18 implementation and verification follow-up

The planned sections above are retained as history. Implemented in existing owners:

- SimilarityCalculator exposes confirmed/conflicting/unresolved identifier evidence
  independently of the ordinary similarity score. Missing identifiers are not a
  score-zero assertion; identifier conflicts still veto. A declared identity
  property defaults admission to strict; strict mode without declarations is
  valid and abstains. Explicit generic deduplication remains compatible, but its
  merge result is not authoritative identity evidence.
- DuplicateDetector admits strict merges only with positive identifier agreement
  and no conflict; type conflicts also veto. Existing group/incremental/explicit
  merge constraints continue to apply. Excluding other candidates never confirms
  the remaining candidate.
- SemanticArtifactBuildRequest accepts identityPropertySchema, reusing the native
  property semantics. The artifact builder always uses strict native resolution,
  refuses a generic injected resolver, preserves aliases/evidence/mention IDs and
  remaps relation endpoints through the same owner. Registry entries explicitly
  distinguish confirmed merged membership from unresolved mentions. No declaration
  means separate unresolved mentions, not name-based identity fallback.
- The policy is validated before extraction, included in rule lineage v2, and
  fenced in SnapshotCheckpoint immutable inputs. Changed identity policy cannot
  silently reuse a checkpoint from another policy. Existing checkpoints lacking
  the policy fence are incompatible; none were migrated or deleted.
- ESG's existing Review policy now requires positive original issuer support and
  rejects elimination-only confirmation. Its contract changes 12 -> 13 to prevent
  reuse of decisions cached under the old semantic policy; no extra model pass.

Affected tests: tests/deduplication/test_identity_constraints.py,
tests/test_project_identity.py, tests/test_semantic_artifact.py and
tests/test_project_checkpoint.py. The artifact worker test compares the same
stubbed typed extraction with/without a trusted identifier declaration: four
unresolved mentions versus two confirmed identities, correct source provenance,
relation remapping, unchanged repeat build, and no identity model call.

Regression-first: the initial focused run reproduced five failures and one pass;
the new checkpoint fence test also failed before the checkpoint fix. Final affected
native regression: **284 passed, 5 subtests passed**, 3 existing provenance
deprecation warnings, 57.77s:

```sh
SEMANTICA_DISABLE_PROGRESS=1 SEMANTICA_DISABLE_JUPYTER_PROGRESS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_project_identity.py tests/test_project_fact_identity.py tests/kg/test_entity_resolver_exact.py tests/deduplication tests/kg/test_entity_pipeline.py tests/kg/test_core_components.py tests/kg/test_graph_builder_with_graph_store.py tests/kg/test_graph_builder_extraction_defaults.py tests/test_semantic_artifact.py tests/test_semantic_artifact_contract.py tests/test_semantic_artifact_native_extraction.py tests/test_project_checkpoint.py tests/test_semantic_artifact_long_context.py
```

Both checkouts passed git diff --check. ESG expanded consumer regression passed
395 tests with 1051 existing deprecation warnings in 58.95s; exact test files are
recorded in its integration audit, following the earlier 120-test focused pass.

### Behavior and merge risks

- This intentionally increases unresolved artifact entities and suppresses
  cross-source relations that depended only on name-based merging. Preserving
  mentions is not a claim that they are distinct real-world entities.
- Declaring a property is an explicit caller trust contract, not automatic source
  verification. Extracted attributes are not authoritative merely because a model
  emitted them. Callers must verify identifier values, scope and source before
  enabling the declaration; the stubbed worker fixture tests transport, not that
  verification. No model-based semantic identity adjudicator was added.
- Identity registry confirmed means the native strict group had positive shared
  identifiers; a singleton remains unresolved for cross-mention identity even if
  it carries an identifier. Conflicts are pairwise evidence, not a global label
  claiming every unmerged mention is a different entity.
- Generic fuzzy dedup remains a different supported purpose, not an alternate
  identity path. Whole-component compatibility can reduce recall and is quadratic
  within generated components; existing approximate candidate generation remains.
- Upstream disposition: pending; adapt/drop this extension if native upstream
  supplies equivalent admission/evidence contracts. Re-run the command above,
  checkpoint fences and worker/request consumers before accepting a merge.
- External non-ESG consumers of the registry schema must verify compatibility
  with the new status field and changed strict semantics before release; library
  worker tests are not evidence of a deployed host migration.

No paid calls, commit/push, deployment, production restart, business data migration,
budget change, real-company adjudication or scale/live acceptance was performed.

## 2026-10-18 superseded: retain native admission, add conflict vetoes only

The owner rejected the strict-identifier policy described above. Its unshipped
implementation is withdrawn, not a supported alternative mode. Native positive
scoring/admission is restored; no identifier match is mandatory, no missing
identifier blocks a native merge, and identifier agreement never upgrades a
native rejection. Explicit conflicts still veto through the same native owners.
The unshipped registry status is removed and lineage/checkpoint policy is updated.
The ESG single Review's original-issuer evidence requirement remains a separate
business rule; it is not a mandatory-ID merge policy.

The authoritative current implementation, regression results and compatibility
limits are in [native resolution conflict veto](2026-10-18-native-resolution-conflict-veto.md).
Earlier tests/results above describe the rejected intermediate design, not the
current contract. Native verification of the correction: 297 passed and 5 subtests.
