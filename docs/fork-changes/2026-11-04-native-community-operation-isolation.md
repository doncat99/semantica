# Exact native community execution and process lifetime

- Record ID: 2026-11-04-native-community-operation-isolation
- Date / author: 2026-11-04 / Codex
- Status: implemented; verification limited to the stated macOS source environment
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus shared uncommitted remediation
- Upstream reference: not newly fetched or reviewed
- Related record: [topology audit](2026-11-04-native-community-topology-resource-gap.md)

## Reason and native capability assessment

`semantic_artifact_builder._semantic_organization` uses the existing
`CommunityDetector.detect_communities(..., algorithm="greedy_modularity")`.
Its native NetworkX owner needs the complete topology and global gain work.
`ParallelismManager` already owns thread/process execution, but its existing
ProcessPoolExecutor path cannot cancel an operation already running. This
change repairs that native owner with a dedicated spawn process for one task;
it does not introduce a scheduler, alternate algorithm or knowledge store.
Actual builder, detector, pipeline exports, manager callers and regressions
were inspected. Host worker termination sends SIGTERM then SIGKILL to its
direct child; therefore native descendants must also observe parent death.

## Approach and actual changes

- `CommunityDetector._to_networkx` populates one NetworkX graph directly through
  the existing `_graph_view` normalization helpers. It removes the intermediate
  GraphView lists/sets, preserving insertion order, loops, isolates, implicit
  valid endpoints and duplicate/reversed-edge collapse. NetworkX pass-through
  and the public community result remain unchanged.
- `ParallelismManager.execute_isolated_task` executes the exact native task
  with cancellation/deadline polling, sampled RSS and deterministic child
  termination/join. A child watcher exits when the parent dies or monitoring
  fails; no task retry or partial result is returned.
- `psutil`, already present at 7.2.2 in every native worker platform lock and
  used by native ResourceScheduler, supplies RSS without a POSIX-only reader.
  It is now an explicit semantic-worker-common dependency; `uv lock --offline`
  resolved 489 packages. No package was installed or release lock regenerated.
- The builder delegates to this owner with a provisional 120-second deadline
  and 1 GiB child RSS limit. ProcessingError becomes
  `NATIVE_COMMUNITY_EXECUTION_FAILED` before native publication. Startup,
  transport, memory, deadline, cancellation, monitor and child-exit failures
  have explicit reasons. Exception causes retain native diagnostic details.
- No persisted contract/data migration, model call, network call, host release
  pin, formal profile write or packaged artifact is part of this change.

## Verification and limitations

Red specifications: intermediate GraphView prohibition failed before direct
conversion; four isolation cases failed before the manager API existed; an
unpicklable task later reproduced a raw startup exception (1 failed, 2 passed).
The latter now produces the typed startup reason and leaves no active child.
Real task exceptions and abrupt child exit are tested, alongside deadline,
cancellation, memory rejection, live memory growth, subsequent healthy work,
and parent SIGKILL while the real child handler is running.

Before the cross-platform RSS adjustment, eight focused owner suites passed
111 tests in 50.02s; paid handoff/recovery/build/publication/embedding selection
passed 72 tests in 43.76s. Actual native→host→installed UA→Learn→SQLite/new
worker passed 1 test (5.10s total); actual reader v3/rebind/range cross-repo
passed 2 tests (1.42s total). These groups overlap earlier evidence; do not sum.
Final results for the adjusted RSS owner are recorded below.

Exact community output is compared with the old GraphView-based construction
for all 64 four-node simple graphs plus malformed/loop/reversed/isolate cases.
The complete organization output SHA256 remains
`1f75e04dd349f60471b066c7802128c575d0598f46d925ada1f50536901493ef`.
Builder failure tests assert the publication entry was never invoked.

**G4 is not passed.** The 50ms Python watcher is sampled and GIL-dependent;
short RSS peaks can escape it. It is not an OS hard allocation ceiling.
Synchronous spawn/pickling and receive/unpickling cannot be interrupted by the
deadline/cancellation loop, despite checks before/after those boundaries.
Input/result copies and parent RSS remain outside the child limit. There is
no algorithm progress API, external-memory greedy engine or proof of realistic
ESG capacity. Windows/Linux source or packaged runs were not performed.
The full primary Case, change-verification, fixed artifact and real ESG
acceptance remain pending. No scope/algorithm/candidate truncation is allowed
to turn these gaps into a pass.

## Upstream merge assessment

Disposition: pending incoming review. Compare native GraphView extraction,
CommunityDetector order/return semantics and ParallelismManager cancellation
before merging. Reuse an equivalent upstream owner if one exists and remove
the superseded implementation. Re-run exact topology/organization goldens,
process failure/lifetime cases, paid recovery and actual cross-repo consumers.
