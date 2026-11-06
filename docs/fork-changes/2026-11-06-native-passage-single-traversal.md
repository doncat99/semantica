# Native passage projection from one bounded traversal

- Record ID: 2026-11-06-native-passage-single-traversal
- Date / author: 2026-11-06 / Codex
- Status: implemented; fixed-artifact qualification passed; real ESG acceptance running
- Fork base revision: 2e4049c6d268eeec2c76f5084da178d029c05f91
- Upstream reference: not inspected
- Related issue / PR / commits / records: pending

## Reason and scope

Offline profiling of an accepted ESG source found 6,959 per-passage text
rereads. Passage projection consumed 161.699 of 256.190 seconds. These are
projection-only measurements, excluding extraction and later native indexing.

## Native capability assessment

- Existing owner: semantic_publication_builder._source_passage_ranges and
  _source_passages; semantic_document_reader remains the sole reader.
- Callers checked: all _source_passage_ranges references, native traversal,
  source-window, source-location and build-body-budget specifications.
- Decision: repair the native traversal, reuse its bounded text windows.
- No second reader, store, global cache, dependency or public export added.

## Approach and actual changes

- Yield the bounded passage text together with its scalar addresses; consume
  it directly instead of reopening the reader for every passage.
- Retain at most 1,600 characters per unfinished passage; clear at newline
  and segment boundaries. Native window, location and cancellation checks stay.
- Preserve segmentation, quotes, evidence identities and stored contracts.
  No stored-data migration or deletion is needed for this change.
- No model calls, network calls or new dependencies. Real profiling explicitly
  rejects any attempt to invoke a model.
- Source-wide concurrency has not been enabled; it would multiply retained
  source working sets. Read-only concurrency is being measured separately.

## Verification and limitations

- Red: test_passage_projection_reads_each_native_window_once observed 8,005
  reads against the two required windows before the owner fix.
- Unicode, whitespace, empty lines, long lines and chunk boundaries have exact
  frozen segmentation oracles. Focused four-file suite passed 54 tests.
- Evidence in host ignored scratch: projection-source6-before-profile.txt,
  projection-source6-profile.txt and projection-concurrency.json.
- Wall-clock comparisons require caution: host load exceeded 100 during the
  post-change run. Call counts provide the less confounded comparison.
- Current fixed artifact passed installed qualification; full ESG acceptance remains outstanding.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Likely overlap: native passage traversal and evidence projection.
- Retain only if upstream still rereads text after native traversal; otherwise
  adopt its equivalent owner and remove superseded implementation.
- Required checks: exact segmentation and quotes, bounded reads, location and
  cancellation contracts, installed artifact and real source projection.

## Dated follow-ups

2026-11-06: record added retrospectively after the implementation; red evidence
and actual inspected base recorded. Verification is not yet claimed complete.

2026-11-06 verification: focused traversal/window/location/body-budget suite
passed 54 tests. Real source 6 retained 6,938 passages; native text reads fell
from 7,021 to 83. Passage traversal profile fell from 161.699 to 41.997 seconds,
but host contention invalidates a whole-projection wall-time speedup claim.
Concurrency 1/2/4 produced no stable gain and remains unchanged. Artifact
87a0f740dd07e5ae0871e8fbb3a88c4ec15f54631d531d9763c9c3d395e05174 passed
relocated native acceptance; full ESG remains open.

2026-11-06 paid-read correction: run 2ace6961 failed at cache.py _accepted_read
after a completed point query exceeded its wall deadline under host contention.
The existing native SqliteCacheBackend remains the owner; accepted_digest,
has_accepted_body, get_accepted and grounded_window callers were inspected.
Removed only the post-completion deadline rejection. Lock wait and SQLite
progress interruption remain bounded; explicit cancellation still rejects a
completed read. No miss, retry, model invocation, receipt change or data deletion
is introduced. The scheduler-delay red specification failed before the fix;
all 18 accepted-handoff tests now pass, including cancellation, locked-owner,
restart, byte limits, writer isolation and decode isolation. Upstream overlap
is the same cache owner and must retain these guarantees. New artifact and real
ESG qualification are required for this additional correction.

2026-11-06 fixed qualification: artifact
sha256:7323f79e33ec909d22c42bea8544ca081480f2ea2136564cce98f97998ab2f5d
passed relocated native acceptance (127.25s), eight installed oracle groups
(89/89, 110.489s) and both isolated lifecycle cases (45.379s), without skipped
checks or paid calls. Strict source/target inventories were verified before
paid-result adoption. Dry/apply reports match: 5,754 extraction results and
3,223 vectors retained; 5,126 embedding windows remain. Real 38-source ESG run
f5befffd-f0a3-4729-bb44-605480c153e6 resumed at 16:42 HKT on that bundle;
parent/descendant RSS monitoring started before build execution. Its ready
publication, full capacity trace and warm rebuild remain required.
