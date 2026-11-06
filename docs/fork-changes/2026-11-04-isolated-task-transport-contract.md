# Isolated task transport contract

- Record ID: 2026-11-04-isolated-task-transport-contract
- Date / author: 2026-11-04 / Codex
- Status: planned; red specifications verified
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty working tree)
- Upstream reference: not inspected
- Related records: 2026-11-04-native-community-operation-isolation.md

## Reason and scope

The current native isolated executor calls multiprocessing spawn and Connection.recv synchronously. Arbitrary input reducers can run in the caller beyond its timeout/cancellation; arbitrary output reducers run outside the deadline polling boundary. This record concerns transport and lifetime, not graph algorithm replacement or qualification of ESG capacity.

## Native capability assessment

Existing owner: semantica/pipeline/parallelism_manager.py::ParallelismManager.execute_isolated_task and _execute_isolated. Actual production caller is semantic_artifact_builder.py::_semantic_organization. Existing tests are tests/pipeline/test_isolated_task.py. Repair this owner in place; do not keep the old pickle path as fallback.

## Approach and actual changes

Planned: restrict isolated tasks to importable handlers and a bounded JSON value transport. Stage descriptors and results in ephemeral bounded files; parent monitors worker cancellation/deadline and RSS independently of the handler GIL. Explicitly reject unsupported input/output instead of invoking arbitrary Python pickle hooks. Preserve complete accepted results; exceeding a limit fails the operation, never truncates candidates.

Parent's pre-existing business graph remains the builder's responsibility. This seam cannot hard-limit the caller process or remove builder-held full lists; it must not claim G4 closure.

## Verification and limitations

Before source changes: `.venv/bin/python -m pytest -q tests/pipeline/test_isolated_task.py -k never_executes_arbitrary_pickle`: 3 failed, 9 deselected in 3.32s. Both input cases execute a 1-second reducer before observing the .2-second deadline/.1-second cancellation; the output reducer executes and returns success. No network/model calls or formal profiles.

Source change and final verification pending. Parent memory, accepted ESG workload, fixed artifacts and full product acceptance are not established.

## Upstream merge assessment

Pending; incoming upstream revision not reviewed. Retain only after verifying the single native owner and current builder/tests use one transport contract.

## 2026-11-04 implementation and scoped verification

Status: implemented; verified only in the stated focused scope.

- Replaced `_execute_isolated` and its multiprocessing Pipe/pickle path in the existing owner with `_isolated_file_operation`, invoked using a fixed subprocess command and primitive argv.
- The current task contract requires an importable Python handler and exact JSON data types. Nested tuples/custom objects/non-finite numbers are rejected explicitly rather than changing semantics. The invocation tuple itself is streamed without copying it to a list. The current community handler's list/dict/scalar input and output conform to this contract.
- `max_transport_bytes` defaults to 16 MiB for each input and result; caller may set a measured policy explicitly. This is a fail-closed transport ceiling, not ESG capacity qualification. A 64-level nesting ceiling and node budget also apply. String encoding proceeds in 16-Ki-character chunks, checking cancellation/deadline. Input/output overflow emits `input_limit`/`output_limit`; unsupported values emit `input_contract`/`output_contract`. No accepted result is truncated.
- Worker output is bounded before success publication, then consumed from an ephemeral private directory after worker exit. The parent does not execute input/output pickle reducers. Parent monitoring samples worker RSS independently of the handler GIL, while the worker watches parent lifetime. Cleanup terminates/kills/reaps the operation before deleting transport files.
- No dependencies, model calls, network calls, algorithm changes or repository data migration. The superseded pickle worker and Pipe transport are physically removed; no compatibility path retained.

Verification:

- Before the source fix, 3 focused transport contract specifications failed in 3.32s (9 deselected), as recorded above.
- After the fix, the then-current isolation suite passed 12 tests in 2.46s.
- Extended isolation + native organization topology + kernel owner regressions passed 63 tests in 50.26s, including exact organization behavior and native error propagation.
- The extended isolation suite passed 17 tests in 3.59s. The output reducer spec now specifically models a receiver-side reconstruction function that would sleep, rather than only a sender-side reducer.

Limits still explicit: subprocess OS creation, bounded filesystem operations and final bounded JSON parsing are synchronous primitives; no claim of a hard real-time guarantee is made. Child RSS is sampled, not an OS allocation ceiling, and descendant processes are not a governed process-tree budget. Parent JSON decode allocation is bounded by transport shape/bytes, but the pre-existing caller graph is not constrained by this owner. Full G4, parent build memory, measured ESG capacity, Windows/Linux packaged runs, fixed artifacts and product acceptance remain unverified. These limitations require owner-level architecture work and must not be hidden behind the focused passing suite.
