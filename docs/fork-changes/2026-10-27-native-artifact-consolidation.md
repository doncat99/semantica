# Native artifact and query consolidation

- Record ID: 2026-10-27-native-artifact-consolidation
- Date / author: 2026-10-27 / Codex
- Status: implementation complete; verification partially blocked
- Fork base revision: d44dd1583a57df34854a3b2300e81f8c4cde37d4
- Upstream reference: local native owners inspected; no incoming upstream merge reviewed
- Related issue / PR / commits / records: pending; no publication authorized

## Reason and scope

The build worker stripped the canonical SemanticArtifact identity, wrote a graph
envelope, and required consumers to reconstruct another snapshot. Its retrieval
revision also differed from the snapshot manifest revision. A real build-to-query
regression reproduced the mismatch. Construction also wrote a temporary provenance
database and vector index which no subsequent query consumed.

## Native capability assessment

- SemanticArtifact owns the persisted document contract; semantic_worker transports
  it, semantic_query_worker consumes it, and explanation workers validate it.
- ExtractionCache and CacheBackend own cache identity and storage. The builder's
  cache subclass duplicated key policy. The native cache now supports explicit
  content identity while its existing execution identity remains the default.
- VectorRetriever.search_similar and ContextRetriever own retrieval decisions.
  The semantic-query adapter consumes native ranking and ordering directly.
- SnapshotCheckpoint is durable receipt/storage integration, not an alternate
  extraction algorithm. Its historical upgrade is offline data migration.
- Native EntityResolver, GraphBuilder, CommunityDetector and CommunitySummarizer
  remain the semantic owners; custom identity-resolution algorithms removed in
  earlier work must not be restored.

## Approach and actual changes

- semantic_worker writes canonical SemanticArtifact bytes directly and explanation
  reads those same bytes; retrieval revision matches retrieval:graph.
- ExtractionCache owns content identity; the project cache subclass is deleted.
  Offline checkpoint migration uses the same native cache key owner.
- Removed unused temporary provenance database and vector-index construction.
  Evidence, locators, model receipts and embeddings remain in their canonical
  artifact locations; this is not deletion of paid historical outputs.
- Host consumer changes and its stored-data upgrade owner are implemented;
  migration of actual production data remains a deployment requirement.
- Removed independent score normalization and final sorting; regression asserts
  native query score and order are preserved.
- Runtime no longer guesses historical document identities. Proven conversion
  is isolated in an offline migration function; runtime rejects unconverted
  opaque identities without mutating or recomputing paid payloads.
- Runtime requires business-content-v1 manifests with canonical business inputs;
  unmarked/unknown layouts are rejected before entry processing. Removed old
  manifest acceptance and top-level recipe interpretation from runtime imports.
- Recipe provenance uses RecipeRef.lineage_payload(); migration preserves the
  original record and separately admits complete current lineage.
- canonicalize_checkpoint provides pure manifest/document dataset conversion,
  delegates entry validation to SnapshotCheckpoint, preserves payloads and
  rejection markers across document key changes, and leaves caller inputs intact.
  It does not certify unmarked extraction datasets or install production files;
  individual extraction recovery helpers are not dataset publication approval.
- Native owners reused include EntityResolver, GraphBuilder relationship
  remapping, EntityMerger/ConflictDetector, CommunityDetector,
  CommunitySummarizer, TemporalVersionManager, ExtractionCache,
  VectorRetriever and ContextRetriever. Remaining product artifact assembly,
  evidence identity and protocol validation are integration responsibilities,
  not alternate extraction/query algorithms.
- Host durable-content migration was implemented and preflights every manifest,
  reference and duplicate digest before deleting only proven duplicate graph
  bytes. Interrupted publication is recoverable.

## Verification and limitations

- Red regression: tests/test_semantic_artifact.py::test_worker_publishes_one_canonical_snapshot_queryable_without_reconstruction
  failed on the original graph envelope (7 strict schema validation errors).
- Native cache regression failed before the identity_policy change; the cache
  suite passed 40 tests after it.
- Host Semantica/sidechat/tool regression: 210 passed; daemon typecheck passed.
- Root guard was blocked by the missing e2e path referenced by another dirty
  knowledge-accumulation document.
- Final root guard rerun passed, including 68 guard tests; the concurrent
  document no longer referenced that missing path. This task did not edit it.
- Fork expanded build/query/checkpoint/cache/native-owner/PDF suite: 208 passed.
  The stale document fixture was corrected; the real worker restart regression
  subsequently passed. After tightening manifest admission, checkpoint and
  offline-upgrade suites passed all 50 tests. Both new manifest rejection cases
  failed before the fix and passed afterwards, preserving original data bytes.
- After adding pure dataset conversion, checkpoint/offline suites passed 55 tests.
  Five new cases cover restored documents, retained rejection state, manifest
  identity admission and input immutability. The initial three cases failed
  before the converter existed and passed after implementation; rejection
  parameterization then expanded coverage to five.
- Final expanded seven-file suite including the converter: 213 passed in 110.40s;
  five existing PyMuPDF/SWIG deprecation warnings, no test failures.
- Full host root typecheck passed; both repositories passed git diff --check.
- Auto Test Case capability-library-prepare / flow library-knowledge-mainline
  first failed to prepare its supervised runtime. A retry reached runtime
  readiness, then timed out checking /chat during preparation. No product
  acceptance pass is claimed. Host evidence directory:
  .tmp/tools-test/auto-test-cfd16dfd-299d-4353-aeab-b44135596807.
- No immutable artifact was published/pinned and no packaged App or production
  build was run. Deployment verification remains required.

## Follow-up verification on 2026-10-27

- Corrected the stale recipe-lineage contract assertion to require the complete
  lineage, including an empty formula-semantics source list; runtime policy is
  unchanged. This fork checkout is the sole source of this remediation.
- Host packaging acceptance now validates canonical SemanticArtifact protocol,
  project/snapshot identity and retrieval manifest revision/source/digest;
  old envelopes and mismatched manifests are rejected without fallback.
- Host tools-pack: 282 passed, 2 skipped across 43 files. Focused host
  worker/query/sidechat/migration/policy/registry regression: 157 passed.
- Fork artifact, contract, query worker, checkpoint and checkpoint-upgrade:
  164 passed in 81.40s using this checkout's complete .venv. Earlier missing
  pdfplumber failures in a borrowed environment are not success evidence.
- Host chat-hook tests: 6 passed after removing an unsupported additional
  receipt-polling loop; both daemon paths persist receipts before generation.
- Library change-verification completed with all stages passed using the
  clean-workspace mock preset, run 09d5781a-3262-4dc4-9219-8d2491153a8b;
  flow duration 101665ms. Case capability-library-prepare, owner journey-library,
  delta keep; no baseline, criteria or gate changes. Evidence is under host
  .tmp/tools-test/auto-test-09d5781a-3262-4dc4-9219-8d2491153a8b/.
- Root guard and typecheck passed. Mock acceptance does not certify packaged
  production ESG performance or real historical-data migration. No artifact
  publication, App packaging/restart or paid production build was performed.

## Upstream merge assessment

### Publication integration on 2026-10-27

- Integrated onto fork main ca34b22dd4df5aace84813d741c2b703a79aca91,
  preserving the newer explanation recovery, project-stage persistence and
  exact native entity resolution. Unqualified score/coherence drafts are excluded.
- Correction to the earlier limits: offline upgrade_checkpoint now recovers
  provable unmarked extraction datasets from verified parsed documents and
  installs through SnapshotCheckpoint's recoverable transaction. Both staged
  and installed datasets are verified before old carriers are physically deleted.
  Production dataset migration remains unperformed.
- The stage-restart test now interrupts retrieval.json writing because the
  unused provenance projection owner was deleted; it still verifies all three
  completed stages survive a new process without recomputation.
- Publication is authorized by the user's explicit request to synchronize the
  necessary repairs to the fork remote. Release and real ESG acceptance are
  subsequent gates, not implied by source tests.
- Integrated regression suite: 288 passed in 92.62s across artifact, contract,
  checkpoint/upgrade, stage restart, exact identity, query, cache, triplet schema,
  native-owner and PDF ownership/dependency tests. Five existing SWIG warnings.
- Additional release/bundle/parser regression: 45 passed with 20 subtests;
  the six stage tests also passed separately after updating the removed hook.
  git diff --check passed. These are source checks, not real ESG acceptance.

- Disposition: pending incoming merge review.
- Overlapping owners: ExtractionCache, ContextRetriever and worker protocols.
- Drop the extension when upstream provides equivalent content identity/offline
  retrieval; retain one owner, never stack compatibility implementations.
- Recheck real build/query/explanation, receipt preservation, source isolation,
  cache/migration and consumer validation after every overlapping upstream merge.
