# Durable accepted extraction handoff in the existing cache owner

- Record ID: 2026-11-04-native-extraction-accepted-handoff
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus shared uncommitted G1 work
- Upstream reference: local merge-base 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0; no new upstream fetch
- Related records: 2026-11-03-native-persistence-g1-audit.md; host deep-relationship-remediation-plan-2026-11.md G1/G3

## Reason and scope

The existing SQLite cache silently skipped failed writes, returned read errors
as misses and allowed TTL/LRU/clear to remove entries. That is valid for an
optional cache, but cannot acknowledge a paid extraction result that has not yet
been adopted by its unique final native owner. This change repairs that same
owner; it does not remove production checkpoint callers or claim G3 completed.

## Native capability assessment

- Owner: `semantic_extract/cache.py::ExtractionCache/SqliteCacheBackend`.
- Callers inspected: `semantic_extract/methods.py` entities/relations/triplets
  ordinary `set/get`, `_make_result_cache/configure_cache`, and
  `semantic_artifact_builder.py::_extract_window_context/_ExtractionCheckpointBackend`.
- The builder still injects the checkpoint backend; methods still use ordinary
  cache calls. Neither is a durable-handoff caller yet. Configuration can still
  fall back to memory in methods; accepted operations explicitly reject memory.
- Existing exports in `semantic_extract/__init__.py` already expose both owners;
  no new export, backend, service, table or result-body copy was introduced.
- Existing backend and isolation regressions were inspected and run.

## Approach and actual changes

`ExtractionCache.accept/get_accepted/release_accepted` delegate to the same
SQLite backend and its existing identity derivation. The single `cache` table
has a nullable `accepted_digest` lifecycle field:

- `accept` serializes one minimal extraction result, commits with SQLite
  `synchronous=FULL`, and returns its SHA-256 only after commit. Repeating the
  same key/value is idempotent; a different protected value is an explicit error.
- Protected rows have no expiry, cannot be evicted or cleared by ordinary cache
  operations, and cannot be overwritten by ordinary `set`. No second value row
  or full context/prompt/request archive is created.
- `get_accepted` treats missing/corrupt/unreadable results as `ProcessingError`,
  never permission to regenerate with a model. Corrupt protected rows survive
  for an explicit recovery decision rather than becoming cache misses.
- `release_accepted` requires the matching accepted-value digest. It is called
  **only after** the final native owner durably adopts the result. Cross-owner
  atomicity is not claimed: a crash before release retains a recoverable value;
  the caller must detect prior native adoption and retry idempotently.
- Limits: 1 MiB serialized value; accepted rows at most backend `max_size` per
  namespace; total protected bytes at most 64 MiB. Exhaustion rejects a new
  acceptance instead of evicting previously accepted paid results. G3 must check
  admission before paid work and stop subsequent paid requests on commit failure.
- The existing `_write_locked` transaction/retry helper is reused with a strict
  mode; failed strict transactions roll back and raise rather than reporting a
  successful handoff. Ordinary optional cache failures retain existing behavior.

The current schema requires `accepted_digest`. Existing databases without that
field are explicitly rejected, with existing paid rows untouched; there is no
runtime migration or old/new schema dispatcher. **G3 must provide controlled
offline transfer of valid paid results before switching callers. Rebuilding or
deleting the old cache/checkpoint is not an acceptable transfer.**

## Verification and limitations

Six new failure specifications initially produced **6 failed / 0.62s** before
the owner change. The final combined focused command:

```text
.venv/bin/python -m pytest -q tests/semantic_extract/test_cache_accepted_handoff.py tests/semantic_extract/test_cache_backends.py tests/semantic_extract/test_extraction_cache_isolation.py
```

Result: **58 passed / 4.18s**. Nine handoff cases cover abrupt `os._exit(73)`,
reopen, expiry/eviction/clear protection, idempotence/conflict, conditional
release, count/entry capacity, memory/disabled/serialization rejection, locked
accept/release rollback, corrupt/read failure and old-schema preservation.
Two parametrized subprocess cases crash before or after native Oxigraph
adoption; the restart uses the accepted value, persists exactly one final native
fact, releases the cache row and executes zero additional model-fixture calls.
The first process executes one model-fixture call. No real provider/network was
called and no official profile was modified.

Remaining integration requirements, not claimed passed:

1. G3 must wire actual extraction and final-owner adoption to these methods and
   use existing task/fee state to distinguish new work from a missing committed
   paid result. An ordinary cache miss is insufficient.
2. A process crash between external provider completion and local acceptance
   cannot be solved by this API alone. Existing task/provider request identity
   must prevent blind paid regeneration; absent durable evidence is a typed gap.
3. Result payload whitelists, processing-identity policy and native adoption
   validation remain producer responsibilities. This generic cache API does not
   authorize storing source text, full context or snapshots as accepted values.
4. The cache cannot interrupt an operating-system fsync stalled inside native
   COMMIT. The product's process deadline remains the final enforcement layer;
   this focused owner test is not packaged runtime cancellation acceptance.
5. Product restart/rebuild, real model token evidence, packaged runtime and Auto
   Test acceptance were not run. No checkpoint was deleted, no data migrated,
   and no commit or release was made.

### Resource and read-contract follow-up

Accepted input now receives a bounded preflight before whole-value JSON
serialization/key creation: at most 8192 nodes, depth 32 and a conservative
1 MiB encoded budget. Strings are counted in 4096-codepoint slices. Only native
JSON fields and the existing Entity/Relation/Triplet types are admitted; custom
codecs, nonfinite floats and oversized integers fail closed. Protected reads
refuse an oversized stored BLOB in SQL before fetching it. Ordinary `get`
refuses protected rows without retrieving their payload, so a caller cannot
turn a protected-read error into a model-generating optional cache miss.

Strict writes use a 0.5-second total deadline including Python owner-lock
acquisition, 100ms SQLite busy waits and cancellation-aware retry waits. A native
SQLite progress handler and a final pre-commit cancellation check roll back
unfinished writes. Cleanup of a closed connection cannot mask the typed failure.
These changes bound this owner's operation; they do not claim the currently
unwired production callers have adopted the contract.

Additional focused tests cover ordinary-read rejection, oversized stored bytes,
large string/list preflight with measured allocation below 256 KiB, native
dataclass round-trip, custom-codec rejection, cancellation, busy database,
closed connection and contended Python lock (failure in less than one second).
Protected reads also accept cancellation, limit owner-lock acquisition to
0.5 seconds and use 100ms SQLite busy waits. The input-key preflight applies to
accept, protected read and release alike.

Follow-up result: **63 passed** for the three cache suites; the preceding run
including both joint publication probes passed **65 tests / 7.96s** (10
unselected publication tests). These numbers are supporting owner evidence,
not G3 production integration or product acceptance.

## Upstream merge assessment

- Disposition: keep pending upstream equivalent.
- Incoming upstream revision: not newly reviewed.
- This extends the existing cache backend/transaction owner. Review overlaps
  in schema, expiry, eviction, clear and serialization when merging upstream.
- Remove this extension if upstream supplies equivalent acknowledged protected
  handoff semantics. Re-run handoff/backend/isolation and actual G3 callers;
  never preserve competing implementations.
