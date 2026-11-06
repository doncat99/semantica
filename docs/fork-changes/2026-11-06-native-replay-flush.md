# Do not force disk flush for already released paid results

- Date: 2026-11-06
- Status: planned
- Inspected fork revision: dbc49009cbc7cf9a29f2069952ae87c574f081b4
- Upstream reference: not inspected; assessment pending.

## Reason and native ownership

A one-second live ESG worker sample spent 78/87 main-thread samples inside
Oxigraph flush. This sample identifies a wait, not whole-run attribution.
`semantic_extract/grounded_window.py::extract_grounded_window.run_stage` and
`semantic_publication_builder.py::_classify_source_batch` flush on every native
receipt replay even when the accepted body has already been released. Their
native adoption owners already flush before releasing paid handoffs.
Callers, extraction crash/restart specifications, and native adoption were
inspected. Repair these owners in place; no alternate storage or execution path.

## Planned change and boundaries

Flush replay only when an accepted body still needs release. Preserve receipt
validation and flush-before-release on that crash-recovery path, and preserve
new paid adoption durability. No recipe, model input, schema or vector changes.
No live runtime patch or interruption of the active paid build.

## Verification

Pending: focused regression rejecting flush during fully released replay,
existing paid crash/restart/failure tests and classification coverage.
No whole-build speedup claimed without measurement; other projection writes
also flush and remain a separate profiling question.

## 2026-11-06 projection follow-up

The source-boundary regression reproduced per-entity forced flush in
`ExtractionRecords.write_identity_projection`; `write_fact_projection` has the
same issue. Their sole production caller is the native builder source loop.
Both writers now leave durability to that loop, which flushes once after all
source projection writes and before staging or project computation. Per-record
validation, atomic derived updates and digest conflict rejection stay intact.
New paid extraction adoption is unchanged. Interrupted derived writes replay
from durable extractions; no recipe, schema, vectors or paid inputs change.

Affected tests: native pipeline, extraction handoff, reduction boundaries,
identity projection and canonical fact publication. The new pipeline test was
observed red before this change. Focused green and timing results pending.
Upstream merge assessment remains pending; no upstream revision inspected.

Verification: 48 tests passed in 42.16s across the five named suites. A local
no-model disk benchmark wrote the same 256 native identity projections: 256
forced flushes took 3.078s; one source-boundary flush took 0.145s. Both runs
reopened their stores and compared every hydrated record for equality. This is
an isolated write-path result under current host load, not an ESG speedup claim.
The runtime artifact and full real build remain to be qualified.

## Upstream merge assessment

Pending; retain the single native handoff owner and recheck durability and
restart specifications if upstream changes adoption or receipt semantics.
