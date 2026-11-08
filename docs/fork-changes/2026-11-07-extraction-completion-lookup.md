# Separate extraction completion lookup from integrity audit

- Record ID: 2026-11-07-extraction-completion-lookup
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope (native source); immutable artifact/App not updated
- Fork base revision: 355107650e1a131b168a4bd9676b2891ed34f520
- Upstream reference: not inspected; local native owner repair
- Related issue / PR / commits / records: user-approved completion/reuse contract

## Reason and scope

Receipt lookup scanned and hashed every owned fact after restart or any native
write. Builder hydrated complete paid results only to discard them for references.
Normal reuse must point-read the existing completion header and return references.
Unread corruption belongs to explicit integrity audit; consumed corruption fails.

## Native capability assessment

- Owner: ExtractionRecords.receipt, commit, read and _verify_receipt; OxigraphStore.
- Consumers: semantic_publication_builder._extract_window_context, grounded_window,
  ClassificationRecords, offline identity migration and native extraction tests.
- Decision: repair existing owner; no second storage, cache or engine.
- Existing commit atomically inserts facts, digests and index, then flushes.

## Approach and actual changes

- Separate bounded completion fields from explicit full fact audit.
- Delete validation proof cache and invalidation; retain native write synchronization.
- Builder requests references and bypasses recovery/hydration on complete native hit.
- Stored facts, physical IDs, receipts and schema remain unchanged. No migration.
- No model/network/dependency cost; no paid results copied or regenerated.
- Planned but not implemented: verification and artifact qualification pending.

## Verification and limitations

- Red: completion lookup after restart scans facts; warm builder constructs provider.
- Focused native tests and boundary qualification pending.
- Normal lookup intentionally does not detect damage in unread payloads.

## Upstream merge assessment

- Disposition: keep native ownership split; upstream incoming revision not reviewed.
- Likely overlaps: extraction records, classification migration, builder handoff.
- Recheck completion-only reads, explicit audits, recovery and reference consumers.

## Dated follow-ups

- 2026-11-07: Implemented the completion/audit split, removed the proof cache,
  kept short raw-write/read synchronization, and made builder reference handoff
  skip providers, hydration and acceptance-cache reads on complete hits. Empty
  entity results need no relation operation; partial results resume unfinished work.
- Consumed entity/relation fields and page positions are checked in bounded reads;
  model-receipt links/required fields are checked on receipt consumption. Missing
  consumed data errors without repurchasing. Normal reads no longer claim to
  verify facts they did not read. Offline maintenance explicitly audits each
  accepted operation; identity migrations retain complete source/target audits.
- Storage-to-consumer contract: exact project/source/material/representation/
  recipe/model/specification/parser/grounding/window identity indexes one physical
  operation. Completion reads fixed predicates only, under a short existing lock;
  no ownedRecord traversal, object restoration or writes. Payload consumers retain
  existing 128-row/262144-byte page limits and operation-size audit limits.
- Final focused command: `.venv/bin/python -m pytest -q
  tests/triplet_store/test_extraction_records.py
  tests/triplet_store/test_identity_projection.py
  tests/triplet_store/test_classification_records.py
  tests/test_native_window_reference_handoff.py
  tests/test_native_extraction_handoff.py
  tests/test_native_reduction_boundaries.py
  tests/test_semantic_artifact_native_extraction.py
  tests/test_native_context_quote_lifecycle.py
  tests/test_request_content_optimization.py
  tests/test_native_maintenance.py tests/test_native_build_lifecycle.py`:
  **116 passed in 47.35s**. Initial completion/reference specifications failed
  against the unchanged owner; corruption expectations were deliberately moved
  to explicit audit and actual-consumption failures. `git diff --check` passed.
- Local persistent fixture (280 entities, 8423 quads), reopen then point lookup:
  first hit 0.729 ms; 1000-hit mean 0.335 ms; five explicit audits mean 93.482 ms.
  Zero added quads. This is not a real ESG end-to-end speedup measurement.
- Acceptance Case `page-knowledge-deep-relationship-project`: keep; primary UI
  owner unchanged, hard gates/baseline unchanged. Native tests provide supporting
  evidence. Product Case and change-verification not rerun for this source repair;
  no installed App/runtime qualification is claimed. No live job/data modified,
  no network/model calls, new result copies or dependencies. Artifact/pin/App
  delivery remains outside this focused source verification.

## Classification reuse follow-up

- Classification now checks the native completion record before acceptance-cache
  recovery, quote hydration, result/receipt reconstruction or writes. Complete
  hits return the existing operation reference. Removed the unused full-source
  classification aggregate and eager reduced-dimension reads.
- Source batch preflight reads quotes once, retaining only evidence addresses and
  exact context digests. The request schema is generated once per source. The
  producer, batching function, recipe/model/taxonomy/context identity are unchanged;
  missing operations still recover accepted paid results before calling models.
- Red specification failed at acceptance-cache lookup on a completed native hit.
  Warm persistent integration forbids payload/recovery reads and verifies one
  quote read per passage, identical reduction identity and no added quads/models.
- Same-data isolated benchmark, 1000 passages, median of three warm runs:
  previous classification 1.392603 s / 3000 quote reads; current 0.215191 s /
  1000 quote reads (6.47 times faster). Zero new model calls or quads, identical
  reduction. This does not establish real ESG total-build latency. One quote
  traversal remains necessary to preserve the existing exact batch input identity.

## Runtime correction and context admission follow-up

- The first packaged real ESG run processed all 38 extraction/projection sources
  with no new model usage, then failed classification: the new completion helper
  incorrectly required `extractionStage` on existing classification operations.
  Classification is identified by its own binding/class/index. Restrict that field
  to entity/relation stages in both commit and lookup; no data rewrite or optional
  compatibility reader. A red fixture reproduced the valid stage-free record.
  Classification, body-budget and paid-rebind regressions: 26 passed in 41.24s.
- Real first-12 extraction elapsed time fell from 400.968s to 348.113s; the slow
  sixth source fell only from 253.022s to 241.943s. This is insufficient evidence
  for a substantial real-build improvement. The earlier isolated classification
  benchmark must not be reported as whole-build acceleration.
- Context admission encoded each growing evidence prefix again to count bytes:
  200 records caused 20,300 record serializations. Count each encoded record once
  and add exact JSON separator bytes, including complete row/header/note groups.
  Removed unused `project` argument; all production callers use context bytes.
  Unicode/escaping and exact-limit/one-byte-overflow regression preserves batch
  identities. Grounding-budget, locations and quote-lifecycle: 30 passed in 27.14s.
- The initial 12-window real-material sample retained identical batches/records/
  digest, but showed no timing improvement (0.687s vs 0.905s). Full slow-source
  comparison and updated artifact/runtime verification remain pending.
- Previous dev artifact 7c366297 was built and launched. Its primary Summary
  Case passed in 24.999s; change-verification run adce59fe was cancelled and is
  not a passing gate. Current correction/context code is not yet in that App.
- Full slow material (191 windows, 48,957 evidence records) produced the exact
  same SHA256 f3cb90cb277f9c815c9a33a3c78ad64ead3da0949b36085a3243da7718978b72:
  old context admission 88.731s, new 44.445s. Processes overlapped, so this is
  preliminary stage evidence, not an isolated benchmark or whole-build guarantee.

## Paid identity correction after packaged verification

- The first packaged real run exposed an identity regression: hashing batch
  admission implementation invalidated unchanged paid extraction inputs. The run
  was cancelled; successful new paid results and receipts were preserved.
- Removed batch admission and byte/token sizing helpers from extraction and
  classification producer hashes. Exact admitted windows/grounding/context remain
  bound in native operation identity; prompt/schema/model/generation producers
  still invalidate recipes. No compatibility reader or fallback was introduced.
- Eight regression specifications failed before the fix; the focused recipe,
  offline rebind, extraction budget and classification budget suite now passes
  **62 tests in 11.21s**.
- Same real ESG source (191 windows, 48957 grounding rows): context admission
  fell from **92.607199s to 37.035578s** with identical output digest
  `f3cb90cb277f9c815c9a33a3c78ad64ead3da0949b36085a3243da7718978b72`.
  Sequential measurements shared the machine with App activity, and are not a
  full-build speedup claim.
- One-time explicit offline metadata rebind is required for the corrected recipe;
  existing native migration audits acceptance and changes indexes in place.
  Physical facts, vectors and paid receipts must not be copied. Migration and
  final packaged real reuse verification are in progress.

- Offline migration completed with the packaged dependency interpreter: 14785
  extraction operations and 85 classifications rebound in place; factsCopied,
  vectorsCopied and receiptsCopied are all zero. Existing vector owner was not
  changed. Maintenance must use runtime dependency versions to verify parser
  identity; development virtualenv dependency differences are rejected.
- Additional focused completion/reference/consumption suite: **95 passed in
  31.84s**. Existing change-verification run 8008d798-8708-46e2-8923-3ae171da72b1
  did not pass: unrelated assistant-routes HTTP owner initialization timed out
  and was skipped, cancelling the group. Deep Relationship primary UI owner
  passed in 47.133s. Final artifact qualification remains separate.

## Real material window reuse verification

- The complete 191-window reuse stage for source
  `1d98ad00-49ed-4361-b6f0-91678efb21ee` completed in **52.500337s**,
  compared with the previous recorded 253.022s (79.25% less elapsed time).
  Provider construction was replaced with a throwing guard and was never called;
  receipt hydration count was zero. All 191 windows returned existing operations.
- Evidence: host `.tmp/reuse-real-source-check.json`; native
  `.tmp/reuse-real-source-check.py`. This uses the packaged dependency interpreter
  with the frozen source implementation, and is not a final App whole-build result.
- Final dev artifact `sha256:8b8f284fcc7ab26ddd8ec69e6ff3720d0fe1914a2e12aacecd14dfbde92eca2c`
  passed native acceptance, host typecheck and guard. Packaging/runtime verification
  continues separately; formal release pin and full project readiness are not implied.

## Completion before model-input preparation (2026-11-07)

- The 38-source installed run reused 8349/8349 extraction windows in 557.244s
  and 8349/8349 vectors in 67.065s. This remains unacceptable lookup overhead;
  those durations do not establish whole-build performance. The old run was
  cancelled through the run API and packaged readers stopped before offline work.
- Profiling source 6 context preparation found 48957 structure hydration calls,
  49685 SQLite connections and 352504 SQL executions. These prepared model inputs
  before the native completion decision, even when no model would be called.
- Extend the existing extraction identity index with one completed-window field:
  ordered grounding digests only. Bind project/source/material/representation,
  actual extraction recipe/model/specification/parser, window bounds and formula
  semantics. Verify every required entity/relation completion header; insert the
  window marker atomically only after all accepted batches are durable. Incomplete
  windows retain existing recovery. Missing/corrupt referenced operations fail
  explicitly; they never silently regenerate paid results.
- Complete lookup now precedes body reads, structural context hydration, batching,
  provider/recovery construction and payload restoration. Scheduler passes window
  addresses and computes source bindings/recipe once per source. Actual consumers
  read native values and ranges only when assembling publication semantics. Tests
  forbid model-input preparation during both lookup and subsequent consumption.
- No new fact, vector, receipt owner, validation cache or dependency. One-time
  existing-data backfill reconstructs the admitted batch references with model
  construction and payload/receipt reads forbidden; writes are restricted to the
  completed-window field in the existing extraction index. This cost is separate
  from warm reuse. Runtime normal completion does not certify unread fact payloads.
- Focused regression: 57 passed in 7.00s (completion/handoff, scheduling, grounding,
  projection, quotes, extraction records); 109 passed in 53.73s (native consumers,
  reduction, lifecycle, maintenance, request optimization and recipe identity).
  New restart specification was red before the fix (address pair could not enter
  completion lookup). Input-field isolation and corrupt batch tests now pass.
- Same source 6 backfill took 53.780306s; subsequent completion lookup including
  source admission/window enumeration took 0.558417s for all 191 windows. This is
  source implementation with packaged dependency versions, not final App timing.
  Full 8349-window measurement and packaged qualification remain in progress.
- Case page-knowledge-deep-relationship-project: keep; hard gates/baseline unchanged.
  No full change-verification rerun for each native edit. Prior unrelated CV failure
  remains a failure and is not promoted by these focused checks.
- Full real-data index upgrade completed: continuation 419.460613s, 7055
  metadata-only inserts; earlier interrupted scratch attempt about 120s is also
  one-time upgrade cost. No fact/vector/receipt copy or model generation.
- New-process warm measurement: all 38 sources / 8349 windows in 13.938722s,
  including source admission and window enumeration, excluding interpreter/store
  startup. Context preparation, provider construction, extraction payload/receipt
  restoration and all writes were forbidden. Quad count stayed 4506269. Evidence
  in host `.tmp/window-completion-{upgrade,warm}.json`. This isolated-path result
  does not claim a complete App build duration; packaging/App check follows.
