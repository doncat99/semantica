# Native streaming task dispatch

- Date: 2026-11-04
- Status: planned; red specification reproduced
- Fork base: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty ongoing G4 work)
- Upstream: not inspected; merge assessment pending

## Native capability assessment

`ParallelismManager._execute_with_threads_fail_fast` already bounds active futures,
but materializes all input Tasks and completed results. Its caller
`semantic_artifact_builder._native_parallel_map` additionally retains ordered results
after delivering them to its callback. Repair this owner with a consuming iterator;
reuse `_execute_task`, retry classification, worker count and cancellation.
No alternate executor, storage or semantic algorithm is introduced.

## Scope and verification

Targets: native manager, builder dispatch caller, streaming task and existing
scheduling/recovery tests. Two red specs fail because `iter_results` is absent.
Keep ordinary `execute_parallel` result collection and priority ordering unchanged.
Streaming submission order is explicitly caller-owned. No stored-data migration,
network/model invocation, dependency or release artifact changes.

This closes scheduler retention only. Builder source assembly, global identity,
facts, topology and reports still need full G4 qualification. Upstream adaptation
must retain bounded submission and consumer-driven release with the same retries.

## 2026-11-04 implementation and verification

Implemented `ParallelismManager.iter_results` with lazy submission bounded by the
worker count. The existing fail-fast list API delegates to it; the builder uses
it directly and returns no result payload from callback tasks. Successful
results are released after consumption. An exhausted transient failure is
reported after draining the same dispatch, preserving recovery semantics;
permanent/fail-fast failures still stop new dispatch.

Verified: streaming dispatch, task recovery, artifact scheduling and isolated
execution suites: 34 passed in 14.74s. An initial combined run exposed immediate
raise incorrectly preventing remaining transient-recovery work; deferred failure
reporting fixed it and the recovery regression passed. An additional builder
callback lifetime regression is being run with the same suites.

The implementation is complete for scheduler retention; overall G4 and release
qualification remain incomplete. No upstream revision or merge was evaluated.
