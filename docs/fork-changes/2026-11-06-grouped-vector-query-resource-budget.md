# Bound grouped native vector query scratch and failure lifecycle

- Record ID: 2026-11-06-grouped-vector-query-resource-budget
- Date / author: 2026-11-06 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (existing uncommitted native integration preserved)
- Upstream reference: not inspected; focused fork-native repair
- Related issue / PR / commits / records: G5 native query acceptance; no commit or artifact publication

## Reason and scope

Grouped exact vector queries retained unbounded visited-ID TEMP scratch, used a 10-second deadline despite the 3-second query gate, and could leak SQLite interruption errors. Deadline checks before a native call did not reject a late result. This repair affects query reads only, with no accepted vector adoption, publication digest, maintenance, or persisted identity changes.

## Native capability assessment

- Existing owner: `SQLiteVecStore.search_native_records` in `semantica/vector_store/sqlite_vec_store.py`.
- Actual caller: `semantic_query.query_semantic_artifact` selects this owner for the knowledge target and translates failures through the existing QueryError boundary. Reviewed native range/publication, embedding handoff, query, vector audit and incremental builder tests.
- Decision: repair native owner. Exact cosine grouping, scoped admission, 256-candidate traversal, complete tie frontier, evidence paging and top-k remain owned by the same algorithm.
- No alternative engine, candidate cap, approximation, fallback or duplicate vector storage was introduced.

## Approach and actual changes

- Owner: enforce 32 MiB TEMP database pages using the actual SQLite TEMP page size and verify the returned max-page setting; configure 512 KiB TEMP cache and retain 8 MiB main cache. Resource exhaustion fails explicitly without returning partial rankings.
- Owner: apply the 3-second deadline, check cancellation/deadline before returning, translate SQLite interruption/full/database errors into ProcessingError, install the progress handler inside protected setup, and clear it before scratch cleanup. Log cleanup failure without hiding a primary error. SQLite FULL text detection supports Python 3.10, where sqlite_errorcode is unavailable.
- Tests: exact existing distribution/paging fixtures plus real SQLite FULL under a deliberately small test budget, cancellation with unrelated SQL after failure, late native call, cleanup fault identity preservation, and same-owner reuse.
- Model/network/dependency/cost impact: none. Existing vectors and accepted digests are untouched; no reset or migration is required.
- Planned but not implemented: whole-process query supervision and total RSS enforcement.

## Verification and limitations

- Red before source repair: 3 failed, 5 passed in 1.19 s; `/Users/huangdon/Documents/OntoScience-od/.tmp/g5-vector-resource-red.log`.
- Focused vector publication/handoff/query/audit/incremental tests: 34 passed in 15.38 s; `/Users/huangdon/Documents/OntoScience-od/.tmp/g5-vector-resource-focused-green.log`.
- Expanded optional set: 35 passed, 16 setup errors; record-worker fixtures attempted to reopen an Oxigraph store held by the same process (`LOCK: No locks available`), before vector-query execution. Evidence: `/Users/huangdon/Documents/OntoScience-od/.tmp/g5-vector-resource-green.log`. This is not a passing worker acceptance result.
- `git diff --check` passed for changed source/test paths.
- No immutable installed artifact rebuilt, no live data touched, no full change-verification or real ESG acceptance performed.
- SQLite page/cache settings bound SQL TEMP data and configured cache, not all sqlite-vec allocations, journals or total process RSS. SQLite progress callbacks cannot preempt an opaque extension call internally; the post-call check rejects a late result but does not prove a hard wall-time interrupt. This focused fix alone does not close G5 whole-process capacity acceptance.

## Upstream merge assessment

- Disposition: keep pending upstream review; native owner repair with no external API change.
- Incoming upstream revision reviewed: none.
- Likely overlap: grouped native query and connection lifecycle.
- Retain until equivalent verified resource/lifecycle controls exist in the owner; do not substitute an approximate algorithm or remove complete tie traversal.
- Required checks after merge: native range/publication, embedding handoff, query, vector audit and incremental builder regressions; qualify packaged product gate separately.

## Dated follow-ups

2026-11-06: Read-only supervision trace confirms the limitation is not closed above this owner. In the consuming OntoScience checkout, `worker-session.ts::SemanticaQuerySession.request` defaults to 120000 ms and `query.ts` invokes it without a deadline override. Timeout rejects before asynchronous close; close sends SIGTERM then SIGKILL after 5000 ms and waits for child close. Abort sends a cancellation frame, waits 2000 ms, then follows the same close path. The one-shot query path has user abort handling but no independent request timer. Python `semantic_query_worker.serve` uses one query thread with cooperative Event cancellation, not a killable per-query deadline. Existing supervision can be reused, but these contracts do not currently guarantee a 3-second hard execution/reap boundary. No consumer files were changed in this scoped repair.

2026-11-06 correction after consumer repair: OntoScience's existing `SemanticaWorkerSession.request` now caps only current-protocol `method=query` requests at 3000 ms, sends SIGKILL on timeout/cancellation and waits for child close before rejecting with the typed timeout/original cancellation. Other method deadlines remain unchanged. `query.ts` deletes its separate one-shot spawning implementation and reuses this supervision owner. The query lane in `runtime.ts` preserves immediate queued cancellation but drains active requests, and no longer passes the signal into the generic `runNative` wrapper that rejected before reaping. Real process regressions deliberately ignore SIGTERM; timeout/cancellation reject only after PID disappearance, queued cancellation remains prompt, and a fresh native owner runs successfully. Red supervision: 2 failed; red runtime wrapper: 2 failed/2 passed. Final selected consumer regressions: 66 passed/45 unselected (three files), `/Users/huangdon/Documents/OntoScience-od/.tmp/g5-query-supervision-final.log`. Source TypeScript check passed; test TypeScript check pending at this append. This closes opaque-call kill/reap supervision for each worker query request in the host path; the synchronous Python owner alone still cannot preempt its extension, and SQL page/cache settings are not whole-process RSS or journal ceilings. Fixed installed artifact and real product acceptance remain separate.

2026-11-06 final consumer type checks: `tsc -p tsconfig.json --noEmit` and `tsc -p tsconfig.tests.json --noEmit` both passed; evidence logs `.tmp/g5-query-supervision-source-typecheck.log` and `.tmp/g5-query-supervision-tests-typecheck.log` in OntoScience. No full change-verification or artifact rebuild was run by this owner.
