# Initialize the existing vector owner before executor dispatch

- Record ID: 2026-11-06-query-native-import-thread
- Date / author: 2026-11-06 / fork contributors
- Status: verified-in-stated-scope
- Fork base revision: 9bf2056718e913f8b997e4ed295432e09cc1d830
- Upstream reference: not inspected
- Related issue / PR / commits / records: Actions 42141214034 and 42145620793;
  [diagnostics record](2026-11-06-windows-native-acceptance-diagnostics.md)

## Reason and scope

Both Windows installed qualifications timed out at the first vector query. The
diagnostic run 42145620793 established that keyword query completed in about
111 ms and semantic query then blocked for 180 seconds. Repeated Python thread
stacks show the executor inside NumPy `_core.multiarray` C-extension loading,
reached through the first import of `SQLiteVecStore`. The serving thread was
waiting for stdin. The same installed bundle had already completed a full build
using NumPy in another process. This isolates the failure to the query process's
native dependency initialization boundary, rather than graph size or model calls.
Python stacks alone do not identify the internal DLL loader/BLAS wait primitive.

## Native capability assessment

- Existing owner: `semantic_query_worker._serve` owns serialized dispatch;
  `semantic_query.query_semantic_artifact` delegates vectors to
  `vector_store.sqlite_vec_store.SQLiteVecStore`, which imports NumPy.
- Checked query startup, executor cancellation, installed acceptance, build worker
  startup and existing query-worker startup/lifecycle tests.
- Repair the existing dispatch owner; no substitute vector store or algorithm.

## Approach and actual changes

- Import the existing vector owner on the serving thread before dispatching a
  semantic query. Preserve deferred loading for keyword, scene, schema and other
  requests; no whole-store data is read during initialization.
- Keep actual query execution on its cancellable executor thread. Do not preload
  dependencies only in acceptance or change the timeout.
- Production change: `semantica/semantic_query_worker.py` only. The same code is
  shipped on every platform; no operating-system branch is introduced.
- No schema, extraction, identity, facts, organization, embedding space, cache
  recipe or stored result semantics change. Existing paid results remain valid;
  bundles need rebuilding for the modified query entrypoint only.
- Test: verify dependency import executes on the serving thread before the
  operation executes on its separate worker thread.

## Verification and limitations

- Before fix: new targeted specification failed (1 failed, 8 deselected).
- `.venv/bin/python -m pytest -q tests/test_semantic_query_worker.py tests/test_semantic_worker_release.py`:
  29 passed in 4.65 seconds.
- Host evidence: `.tmp/g8-windows-native-import-red.log` and
  `.tmp/g8-windows-native-import-green.log`; `git diff --check` passed.
- Windows installed rerun pending. Local execution establishes thread ownership,
  not Windows DLL behavior. The exact native wait primitive remains unknown;
  installed qualification must establish whether this removes the observed wait.
- No full host regression, model call, live store access or dev rebuild performed.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Likely overlap: query-worker dispatch, native vector dependency imports.
- Retain the thread ownership guarantee while native dependencies can first load
  in executor threads; adapt at the same owner if upstream changes initialization.
- Required checks: query lifecycle/cancellation/startup tests and Windows installed
  keyword plus semantic acceptance using the immutable relocated runtime.

## Dated follow-ups

2026-11-06: local regression verified; Windows installation qualification and
formal release remain pending.
