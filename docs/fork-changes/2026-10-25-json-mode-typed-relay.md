# Typed relay JSON mode

- Record ID: 2026-10-25-json-mode-typed-relay
- Date / author: 2026-10-25 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 2d20ba37d2ca1bd77e197322292081d005661a85 (dirty checkout)
- Upstream reference: not inspected; merge assessment pending
- Related issue / PR / commits / records: publication pending

## Reason and scope

OpenCC rejected typed extraction with HTTP 400: `This response_format type is
unavailable now`. Current DeepSeek Flash supports JSON object mode, not the
strict JSON-schema wire mode previously selected by this relay.

## Native capability assessment

The actual owner is `semantica/semantic_artifact_builder.py::_ProjectModelProvider`
(`generate_typed`, `generate`). Grounded typed extraction calls this provider;
`tests/test_semantic_artifact_native_extraction.py` exercises its relay and
Pydantic admission. Repair this owner, not the separate generic LLM provider.
Existing `_relay_cache_key` and extraction checkpoints remain the owners of
reuse. No second implementation or fallback is introduced.

## Approach and actual changes

- Keep `response_format.type=json_object`; append `schema.model_json_schema()`
  to the request prompt instead of sending `json_schema` on the wire.
- Preserve local `model_validate_json` and its validation context. Malformed or
  invalid results fail directly, without retrying another output format.
- Remove the dependency on OpenAI's private strict-schema conversion helper.
- Add valid/invalid/non-JSON regression cases, asserting exactly one relay call.
- Do not change checkpoint/cache identity, migrate/delete data, or recompute
  historical results. New requests include schema prompt tokens.
- Source changes are not yet published or packaged into the installed App.

## Verification and limitations

External source tests used an isolated test environment in the consuming
OntoScience checkout, with canonical source on PYTHONPATH (test only).
Focused typed-relay and cause tests: 4 passed, 19 deselected.
`test_semantic_artifact_native_extraction.py` plus
`test_kernel_owner_regressions.py`: 60 passed, 2 failed.
Failures are `test_parallel_extraction_failure_retains_task_and_window_context`
(additional attempts field) and
`test_native_extraction_preserves_retryable_relay_failure` (false vs true).
They mock grounded extraction and do not invoke the changed typed-provider
path; baseline reproduction has not been performed. Do not claim full-suite
success. Evidence in consumer `.tmp/esg-json-native-tests.log`.

A single consumer replay using JSON object mode, explicit thinking disabled,
and local result admission returned HTTP 200 and actual model `deepseek-flash`.
Evidence: consumer `.tmp/esg-json-object-live-probe.log`; no production cache
write. This checks provider compatibility, not installed native deployment or
absence of unreported internal reasoning. Full App build remains unverified.

## Upstream merge assessment

2026-10-25 release preparation: the two broader failures above were stale retry
expectations, now corrected with exact attempt-count assertions in the task-local
recovery record. Combined extraction/kernel/recovery/upgrade rerun: 84 passed.
This supersedes the earlier unresolved test result, not the App deployment gap.

- Disposition: pending; incoming upstream revision not yet reviewed.
- Likely overlap: `_ProjectModelProvider` typed response formatting.
- Retain one native owner. If upstream provides supported JSON mode and local
  validation, adapt or drop this patch rather than layering another fallback.
- After merge, run typed admission, relay error, native extraction and consumer
  provider tests, then immutable native artifact acceptance.
