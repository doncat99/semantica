# Clean native keyword query scratch on cancellation and completion

- Record ID: 2026-11-06-keyword-query-scratch-cleanup
- Date / author: 2026-11-06 / Codex
- Status: verified-in-stated-scope
- Fork base revision: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` plus the existing uncommitted native-owner work
- Upstream reference: not inspected in this focused repair
- Related records: [native keyword oracle](2026-11-04-native-keyword-g5-oracle.md)

## Reason and scope

Current installed artifact `sha256:7bcdf8f8ed3c6348c48a482ca2c6b6ff856b073fdf9a5239d1acb2e8f40a9cb7` passes the positional and incremental keyword oracles, but cancellation during candidate fill leaves both the query progress handler and `native_candidates` TEMP table on the connection. An unrelated subsequent SQL statement then fails `OperationalError: interrupted`; successful queries also retain the TEMP table.

The isolated fixture reproduced this against the installed owner before repair. This source change prepares the next artifact; it does not mutate or qualify the currently running artifact or close G5.

## Native capability assessment

- Owner: `semantica/explorer/search_index.py::GraphSearchIndex.search_native_positions`.
- Actual production caller: `semantica/semantic_query.py::query_semantic_artifact`, which wraps `ProcessingError`/SQLite errors in its existing `QueryError` and closes the lexical owner in `finally`. Its keyword branch does not invoke the vector owner or embedding relay.
- Request-local cancellation owner: `semantic_worker_context.check_query_cancellation` raises `ProcessingError('query canceled')`.
- Tests inspected: `test_native_keyword_owner.py`, `test_native_query.py`, `test_semantic_query_worker.py`; current installed positional/vector/incremental tests also provided pre-repair evidence.
- Decision: repair the existing native owner. No alternate reader/index, protocol, export, fallback or data store is introduced.

## Approach and actual changes

- Move progress-handler installation and TEMP setup/fill inside the existing protected query lifetime.
- In `finally`, remove the potentially expired handler before dropping TEMP scratch, on success, cancellation, deadline and other errors.
- If scratch cleanup itself fails, propagate its error when there is no original failure. Otherwise log the cleanup failure and preserve the original error and traceback.
- Add regression specifications for actual cancellation and deadline during fill, unrelated SQL reuse while the old cancellation/deadline remains active, exact subsequent search, successful and invalid-cursor cleanup, and cleanup-error preservation of the original cancellation object.
- Query budgets, candidate recall, source scope, cursor/response contract and Python >=3.10 library support remain unchanged. No stored-data migration, model/network operation or dependency change is needed.
- Changed write set: this record, `search_index.py`, and `tests/test_native_keyword_owner.py` only.

## Verification and limitations

- Red before source repair: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_native_keyword_owner.py -k 'interrupted_candidate or cleanup_failure'`: **3 failed / 4 deselected, 1.26s**. Cancellation/deadline poison the connection; cleanup diagnostics are absent. Host scratch evidence: `.tmp/g5-keyword-cleanup-red.log`.
- Final owner regression: same environment/flags, full `tests/test_native_keyword_owner.py`: **7 passed, 2.03s**. Evidence: host `.tmp/g5-keyword-cleanup-green.log`.
- Caller regression: same environment/flags, `tests/test_native_query.py tests/test_semantic_query_worker.py`: **13 passed, 5.69s**. Evidence: host `.tmp/g5-keyword-callers-green.log`.
- These are canonical-fork source tests, not qualification of a newly packaged artifact. The existing 7bcdf8 installed regression and failure probe are pre-repair evidence only. New packaging and installed regression remain required after integration.
- No live stores, real ESG queries/model calls, full change-verification, baseline changes or gate changes in this repair. Explicit TEMP capacity and real ESG product/resource acceptance remain separate G5 exits.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Likely overlap: native keyword query setup/fill and SQLite progress-handler/TEMP lifetimes.
- Retain while the native owner has this lifecycle; adapt or remove if upstream supplies equivalent cancellation-safe cleanup in the canonical owner.
- After merge, rerun keyword owner, native query and serial worker cancellation tests, followed by installed artifact oracles. Preserve complete positional recall and no lexical embedding work.
