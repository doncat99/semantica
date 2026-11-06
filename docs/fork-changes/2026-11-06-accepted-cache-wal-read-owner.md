# Bounded accepted-result reads independent of writer commits

- Date: 2026-11-06; status: verified in focused scope, full ESG acceptance pending.
- Owner: existing `SqliteCacheBackend`; no second cache or runtime fallback.
- Root cause: accepted identity point reads shared the writer mutex/connection.
  Writer transaction/fsync and paid JSON decode held that mutex, so 16 recovery
  readers could exhaust their unchanged 0.5 second budget without running SQL.
  Original installed-runtime reproduction failed 16/16 reads. Two red tests
  reproduce writer-commit and decode blocking at the original cache.py:717.
- Fix: one fixed additional WAL read-only connection and reader mutex, never
  per-thread/per-request connections. Short snapshot reads preserve receipt/body
  atomicity while remaining independent of writer fsync. Hash/JSON decode occurs
  after the bounded blob read and outside both database mutexes. Writer
  transaction, FULL durability, cancellation and the 0.5 second limits remain.
- Pending count/byte admission now uses a partial expression index on namespace
  and length(value), excluding ordinary cache bodies and retired receipts.
  Its capacity query visits fewer than 100 SQLite VM instructions with 2,000
  ordinary 8 KiB bodies and 10,000 retired receipts; capacity limits are unchanged.
- Canonical codecs, keys, model inputs, native receipts and vectors are unchanged.
  Whole-runtime processing identity still changes, requiring explicit offline
  adoption; normal reads never inspect the old recipe.
- Dedicated `--cache-owner-repair-inventory` certificate accepts only exact 18e
  processing and exact reviewed before/after cache bytes. Every other runtime
  byte and complete Python inventory must match. It reuses the fixed 875-window
  paid-input proof, normalizing only its already-certified source release, then
  revalidates 1,582 extraction operations and 830 vectors through canonical
  adoption. Apply requires the exact successful dry certificate; model calls
  and failed pending envelopes are never synthesized.
- Focused cache/backends/isolation/native handoff and maintenance suite:
  108 passed in 22.67 seconds before dedicated certificate tests. Red evidence:
  host `.tmp/g4-accepted-lock-red.log`; fixed-runtime contention reproduction:
  `.tmp/g4-accepted-lock-repro.json`. Final artifact dry/apply and real ESG
  completion remain separate integration gates. No live native data was opened
  during diagnosis or implementation.
