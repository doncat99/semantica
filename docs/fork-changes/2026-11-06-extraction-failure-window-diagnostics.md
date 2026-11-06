# Extraction failure window and completion diagnostics

- Record ID: 2026-11-06-extraction-failure-window-diagnostics
- Date / author: 2026-11-06 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected; local native diagnostic repair
- Related issue / PR / commits / records: G4 ESG run 6e7b6051-6b94-4123-b969-f27bd1f453cd

## Reason and scope

Concurrent extraction failures lost their scheduler window identity when the worker
unwrapped a model-output cause before collecting the outer parallel context. The
failed ESG source had two distinct failed windows; the older response cannot
reliably identify their precise window or incomplete finish reason.

## Native capability assessment

- Existing owners: `semantic_worker._response`, builder `_safe_diagnostic`, and
  `semantic_extract.providers` typed response validation.
- Inspected callers: native parallel-map error context, typed extraction wrapping,
  worker response serialization, and host relay diagnostic consumers.
- Decision: repair these current owners. No alternate extraction or response store.

## Approach and actual changes

- Collect outer scheduler context before cause unwrapping; preserve safe task,
  window and attempt identity on the final worker failure.
- Permit only enumerated completion reasons and nonnegative integer completion
  facts in gateway diagnostics. Preserve output character count and attempt count
  when JSON schema validation fails; never retain raw failed response text.
- Files: `semantica/semantic_worker.py`, `semantica/semantic_publication_builder.py`,
  `semantica/semantic_extract/providers.py`, and the existing validation diagnostic
  tests.
- No model, prompt, accepted extraction schema, retry policy or vector-space change.
  Whole-code processing digests change; accepted result reuse must use the existing
  certified recipe-rebind procedure, not assume artifact digest equality.

## Verification and limitations

- Window-context regressions: red 2 failed / 5 passed, then 7 passed.
- Safe completion-fact and invalid-JSON regressions reproduced before repair.
- `.venv/bin/python -m pytest -q tests/test_semantic_worker_validation_diagnostics.py tests/test_semantic_artifact.py -k 'diagnostic or invalid_json_reports'`:
  11 passed, 28 deselected. Evidence `.tmp/g4-output-facts-native-green.log`.
- No real model rerun, full release qualification or G4 capacity claim in this repair.
  The original lost finish reason cannot be reconstructed from this change.

## Upstream merge assessment

- Disposition: keep pending upstream review; this repairs the current error chain.
- Incoming upstream revision: not reviewed.
- Likely overlap: worker failure serialization and provider validation diagnostics.
- After merge: repeat scheduler-context, typed-wrapper and safe-projection tests;
  retain explicit rejection of response text and invalid diagnostic values.

## Dated follow-ups

2026-11-06: parent owns final artifact qualification and canonical resume of only
missing extraction operations, preserving accepted successful windows.
