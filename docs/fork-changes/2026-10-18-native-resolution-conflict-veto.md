# Restore native positive resolution; retain conflict veto

- Record ID: 2026-10-18-native-resolution-conflict-veto
- Date / author: 2026-10-18 / Codex, authorized by fork owner
- Status: implemented; affected native regressions verified offline; not released
- Fork base revision: c1fe1d203766c00186e59a19ec27050133d86c14 plus local changes
- Upstream reference: not refreshed; no upstream merge performed
- Related records: 2026-10-18-positive-identity-admission.md,
  2026-10-18-native-identity-constraints.md

## Reason and scope

The owner rejected mandatory identifier admission. Retain Semantica's native
positive decision and add only explicit conflict vetoes. Missing identifiers are
not conflicts; elimination alone never makes an otherwise rejected pair pass.
Withdraw the unshipped strict option, identifier score-one shortcut and
confirmed/unresolved artifact labels, not the original native resolution pipeline.

## Native capability assessment

- Reuse SimilarityCalculator scoring and candidate generation, DuplicateDetector
  admission/group compatibility, EntityResolver and EntityMerger materialization.
- Inspected native owners/callers with rg, project identity, deduplication, artifact
  worker/schema and checkpoint tests, prior change records and current dirty state.
- Restore native scoring for nonconflicting input. Property declarations remain
  only to interpret caller-supplied conflicts; artifact projection delegates.
- No alternate resolver, model, prompt, company rule, identifier list or dependency.

## Approach and actual changes

Implemented in the existing native owners:

- SimilarityCalculator: remove mandatory/optional require_identity admission,
  identifier-match score-one shortcut and identity_status; restore native property
  scoring (including empty property similarity of 1.0). Explicit legacy
  require_identity configuration fails rather than silently applying a different
  policy. identity_evidence retains comparable matches/conflicts for diagnostics;
  only conflicts veto. No identifier-field or company-specific names are embedded.
- DuplicateDetector: native score/confidence still decide positive eligibility;
  declared comparable identifier conflicts and existing type conflicts veto.
  Preserve pair, whole-component, incremental, pre-result-cap and explicit merge
  protections. No sole-survivor promotion or new identity scorer.
- Semantic artifact builder/schema: delegate to the native resolver, without a
  required identifier match or injected strict resolver. Remove the unshipped
  registry status field. Keep aliases, mention provenance, evidence and endpoint
  remapping. identityPropertySchema supplies conflict semantics only.
- Artifact rule lineage is v3, including native-conflict-veto-v1 and the declared
  schema. SnapshotCheckpoint fences that policy in existing processing contracts;
  changed policies cannot silently reuse old output/checkpoints. Nothing deleted.

Callers/tests inspected: EntityResolver, EntityMerger, native batch/incremental
detection, project identity, semantic artifact worker/schema and checkpoint;
ESG Review remains separate and does not introduce a second merge algorithm.

## Verification and limitations

Regression-first run reproduced 5 failures and 1 pass before correction. The
final expanded no-conflict equivalence matrix covers same/near/unrelated names
with missing, incomplete, different-scope and matching properties: declarations
must preserve both native score and native resolution. Additional tests cover
conflict veto, aliases, bridge/cap ambiguity, explicit/incremental merging,
low-score non-promotion, worker provenance/endpoints, and checkpoint fences.

Final affected native regression: **297 passed, 5 subtests passed**, 3 existing
ProvenanceTracker deprecation warnings, 66.44s. Exact command:

```sh
SEMANTICA_DISABLE_PROGRESS=1 SEMANTICA_DISABLE_JUPYTER_PROGRESS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_project_identity.py tests/test_project_fact_identity.py tests/kg/test_entity_resolver_exact.py tests/deduplication tests/kg/test_entity_pipeline.py tests/kg/test_core_components.py tests/kg/test_graph_builder_with_graph_store.py tests/kg/test_graph_builder_extraction_defaults.py tests/test_semantic_artifact.py tests/test_semantic_artifact_contract.py tests/test_semantic_artifact_native_extraction.py tests/test_project_checkpoint.py tests/test_semantic_artifact_long_context.py
```

git diff --check passed. No deployment, paid requests, business data or
dependency-pin changes. ESG consumer verification recorded in its integration
audit; installed consumer tests are not a deployment test of this uncommitted fork.
The existing 10-file ESG consumer regression passed 395 tests with 1051 existing
deprecation warnings in 70.09s (Review/evidence, worker protocol, official-source,
Redis/minimal runtime, semantic boundary, governance, adapter and transport).

Limitations: declarations rely on caller-verified values and scope, not automatic
source validation. Missing/different scopes are not comparable and do not veto.
Native fuzzy merges are not documentary issuer confirmation. Whole-component
compatibility can suppress otherwise eligible pairs in ambiguous components and
is quadratic within those components; no scale benchmark or independently
adjudicated real-company accuracy result. Prior strict-policy checkpoints and
intermediate snapshots with registry status may be incompatible; they were not
migrated, discarded or silently reused.

## Upstream merge assessment

Pending. Inspect equivalent native conflict handling before retaining/adapting these
changes. Re-run native scoring, no-conflict equivalence, pair/group/incremental/
explicit merge, worker/schema, checkpoint and ESG Review regressions after merge.
No claim of real-company adjudication or scale acceptance.

## 2026-10-18 installed-wheel and source-derived universe qualification

ESG froze 5,401 distinct CIK/name mentions for 5,356 issuers from its SEC seed and
historical company snapshot, retaining source hashes and row provenance. Only
45 same-CIK name-variant pairs exist; this is source-derived reference evidence,
not independently adjudicated or period-qualified gold. No model/network calls
occur during resolution. The benchmark delegates exclusively to EntityResolver.

On identical full-universe inputs, the previously installed consumer package
merged 795,019 cross-CIK pairs with supplied scoped registry IDs. This candidate
merged zero cross-CIK pairs; same-CIK name-pair recall increased from 21/45 to
27/45. Identifier mode took 4.15s in the Python 3.13 candidate environment.
Names-only output remains identical in counts to the baseline: 45 resolved
entities, 797,557 wrong pairs, 21/45 correct pairs. Native first-letter blocking,
Jaro-Winkler/default weighted scoring and connected components are unsuitable
as documentary company confirmation on this sparse input. This change has not
retuned them or introduced mandatory identifiers. The remaining 18 misses must
not be silently promoted by a shared identifier; historical names also need
effective-period/source adjudication before alias enrichment.

Packaging verification caught a dirty build/lib including retired identity.py
and semantic_artifact_pipeline.py in the first wheel. That wheel (SHA256
b5a76fa67940945ca7b258305caab2d634d94336a567c6d7421b4cacdac36a7f)
was rejected before installation or deployment. The generated build directory
was moved intact to /tmp/semantica-build-before-clean.VEtuP4/build and rebuilt.
The clean wheel (SHA256
809552d50cb2fda6513e884f881a4b55ee239db66a02af2d2b1eaf0e8f57a10c)
contains exactly the 435 current semantica Python sources, byte-for-byte, with
neither retired module. Clean build and inventory equality are required when
assessing a local release artifact; a successful build command alone is insufficient.

Source regressions repeated: 297 passed and 5 subtests, 57.99s. Installed clean
wheel regressions from copied tests outside the checkout, with package origin
asserted: 297 passed and 5 subtests, 39.92s. Both have 3 existing provenance
deprecation warnings. Initial broader installed tests exposed absent blake3
(38 failed/259 passed); installing the existing semantic-worker extra's declared
blake3==1.0.8 resolved them. This is a test environment prerequisite, not a new
identity dependency; the full document-processing extra was not qualified here.

ESG evidence: data/evaluation/native-identity-source-20261018.json,
data/audits/native-identity-installed-baseline-20261018.json,
data/audits/native-identity-candidate-wheel-20261018.json and
data/audits/native-conflict-veto-wheel-complete-pytest-20261018.xml.
Runtime/package deployment and report delivery are separate consumer checks.
Wall-clock timings are single runs, not a throughput SLA or isolated performance
comparison. Independent issuer adjudication, real report semantic/multi-hop
delivery and continuous production qualification remain unpassed.
