# Preserve paid-result reuse across transient read contention

- Record ID: 2026-11-07-accepted-read-contention
- Date / author: 2026-11-07 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 6cb80459a81eb4098f6c5073fe09eea345b3bf50
- Upstream reference: not inspected
- Related issue / PR / commits / records: current KnowledgeHub G4 remediation

## Reason and scope

The real 38-source ESG build failed at cache.py:734 while waiting for the
shared read owner. A transient 500ms lock timeout was treated as a permanent
extraction failure. The failing branch runs before SQL; it does not establish a
bad receipt or unavailable model. The precise scheduling pause has no trace.

## Native capability assessment

- Existing owner: `SqliteCacheBackend._accepted_read`, `accepted_digest`,
  `get_accepted` and `has_accepted_body`; point reads use existing primary keys.
- Callers inspected: `extract_grounded_window.run_stage`, provider error
  classification, builder `_native_parallel_map`, `ParallelismManager._execute_task`.
- Decision: repair existing owner. Reuse window/task bounded retry semantics;
  introduce no connection pool, alternative reader, model path or dependency.
- Existing cache and grounded-window specifications inspected.

## Approach and actual changes

- Only owner-lock acquisition expiry raises `AcceptedReadContention` with
  `retryable=True`. Keep the existing 500ms single-read budget.
- Acquire in at most 50ms intervals to observe cancellation promptly.
- SQL errors, missing/corrupt receipts and cancellation remain non-retryable.
- Existing recovery reads restore paid results instead of rejecting receipts or
  repeating model calls. No storage/schema/cache identity changes or migration.
- No network/model calls or production-data writes are needed for these tests.

## Verification and limitations

- Red: three new contention specifications failed against the inspected source.
- Green: `.venv/bin/python -m pytest -q tests/semantic_extract/test_cache_accepted_handoff.py -k contended_paid_read`: 3 passed.
- Combined cache, grounded-window and crash-handoff run: 44 passed, 1 failed.
  The unchanged non-durable test
  `test_grounded_window_records_candidate_rejections_on_model_receipt` expects
  `rejected_candidates`; the current producer writes `rejected_count`. This
  assertion does not execute the cache owner and remains a separate known gap.
- Focused cache and native crash-handoff run: 37 passed in 19.54s.
- `git diff --check`: passed.
- Tests cover transient contention recovery, no receipt rejection/model call,
  prompt cancellation and the existing two-window by two-task attempt ceiling.
- Real ESG, immutable artifact qualification and App acceptance remain root-owned.
- Bounded retries can still fail if contention persists; this is not an unlimited
  wait or a claim that a scheduler pause has become impossible.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Likely conflicts: persistent extraction cache and provider retry classification.
- Retain only while upstream lacks equivalent typed transient contention handling.
- Re-run cache, grounded-window and durable handoff tests after any overlapping merge.
