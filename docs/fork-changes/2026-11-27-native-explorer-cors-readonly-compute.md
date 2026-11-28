# Native Explorer cross-origin reads and read-only computation

- Record ID: 2026-11-27-native-explorer-cors-readonly-compute
- Date / author: 2026-11-27 / Codex
- Status: implemented-unverified
- Fork base revision: `1a76b294709472a1f6c541c53cbfb025f31b5ad3`
- Upstream reference: not inspected in this change
- Related issue / PR / commits / records: OntoScience Knowledge Map API integration audit

## Reason and scope

The OntoScience host serves the Explorer UI from one origin and connects it to
the per-session native service on another origin with `X-API-Key`. Browser
preflight and middleware ordering could hide native typed responses behind a
generic network failure. The embedded viewer also needs read-only computation
routes to work without permitting graph writes.

## Native capability assessment

- Existing owner and inspected files/symbols: `explorer/app.py:create_app`,
  native service/scope middleware, `routes/enrich.py:run_reasoning`, and
  `tests/explorer/test_native_service.py`.
- Actual callers / config / exports / tests / recent removals checked: the
  host Explorer request bridge uses `X-API-Key`; native-service tests exercise
  browser preflight and API responses.
- Decision: repair native owners.
- Evidence no second implementation is introduced: existing FastAPI CORS and
  read-only middleware remain the sole request and mutation boundaries.

## Approach and actual changes

- `explorer/app.py`: put CORS outside native request fencing, permit native
  non-credentialed cross-origin requests, allow the required PATCH preflight,
  and admit only read-only calculation POSTs through the published-graph fence.
- `explorer/routes/enrich.py`: reject `apply_to_graph=true` in native/read-only
  sessions even if the caller bypasses the frontend control.
- `tests/explorer/test_native_service.py`: cover CORS, typed native boundary
  errors, read-only calculation requests and write rejection.
- No persisted-data, model, dependency or paid-work changes.

## Verification and limitations

- `.venv/bin/python -m pytest tests/explorer/test_native_service.py -q`:
  10 passed, 1 dependency deprecation warning.
- The isolated OntoScience browser acceptance is still running; this record
  remains `implemented-unverified` until its result is collected.
- The allowlist must remain limited to operations verified not to mutate the
  published graph.

## Upstream merge assessment

- Disposition: pending; this change repairs the native session integration
  required by the OntoScience host.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: CORS and read-only middleware
  in `explorer/app.py`, plus reasoning route in `routes/enrich.py`.
- Conditions to retain, adapt or remove this change: retain only while the
  host uses cross-origin session API calls and the published graph remains
  read-only.
- Required consumer/regression checks after merge: native Explorer service
  tests and the host's isolated browser acceptance.

## Dated follow-ups

- 2026-11-27: implementation and fork test pass recorded; browser acceptance
  result pending.
