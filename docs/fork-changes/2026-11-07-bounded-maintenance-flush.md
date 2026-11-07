# Bound offline paid-result adoption durability flushes

- Date: 2026-11-07
- Base inspected: 765c0ef2d1e868e074ca31068e9db90a0672a9c2 on main
- Status: source implementation and focused regression verified; not shipped in the existing frozen App

## Native owner and cause

`ExtractionRecords.commit` already atomically writes a bounded extraction and receipt, then calls `OxigraphStore.flush`. Offline `rebind_paid_native_results.adopt` repeated this for every result. The recorded real adoption process sampled RocksDB flush/compaction as dominant. This is durability-boundary amplification, not evidence that unrelated project data was being recomputed.

## Change and affected callers

Reuse OxigraphStore, adding `batch_writes` for caller-bounded offline maintenance. The existing rebind caller groups 16 windows, at most 32 extraction operations, each limited by the existing 2 MiB serialized-operation budget (64 MiB per boundary). Each operation remains atomic; the batch is explicitly not a rollback transaction. Writes are serialized under the existing native lock. Ordinary runtime calls keep their existing flush semantics.

Keep accepted recovery envelopes until the context's flush succeeds. On exceptions, attempt the durability boundary and preserve envelopes. After interruption, verify existing native operations and release remaining envelopes only after a successful flush. No model calls, replacement storage, runtime hotpatch or new dependency. Existing embedding and classification owners remain unchanged.

## Validation and limitations

Red: three native batch specifications failed for missing batch_writes before implementation.
Green: 51 focused native storage/extraction/maintenance regressions passed in 3.85 seconds. Additional maintenance fault injection verifies no envelopes are released on failed flush, reopening resumes without recomputation, and repeated apply leaves no pending envelope. Only its two parameterized cases are rerun after that caller refinement.

No full App rebuild, real-data re-adoption, benchmark or full change-verification repeated for this source follow-up. Existing frozen-artifact evidence does not qualify this unshipped native change. Actual end-to-end speedup is not measured; flush-frequency reduction follows the bounded grouping. Normal queries, model recipe and semantic data are unchanged; the source change must follow immutable artifact publication before runtime use.

## Upstream assessment

Pending: no new upstream revision inspected. Retain the native owner and focused recovery tests when merging; do not add a parallel maintenance storage path.
