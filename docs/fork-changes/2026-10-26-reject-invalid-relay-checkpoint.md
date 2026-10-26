# Reject invalid typed relay checkpoints before retry

- Record ID: 2026-10-26-reject-invalid-relay-checkpoint
- Date / author: 2026-10-26 / Codex
- Status: implemented-unverified
- Fork base revision: f69d598466e7877a795b1bbccd35231910858558
- Upstream reference: not inspected for this fix
- Related issue / PR / commits / records: pending

## Reason and scope

The typed provider already had a native validation retry loop, but durable relay
responses were written to the project checkpoint before validation and were not
rejected before the next attempt. A retry therefore restored the same invalid
response instead of making a new model request. This caused source
classification builds to fail with `MODEL_OUTPUT_SCHEMA_INVALID` despite the
configured retry budget. The scope is limited to invalid typed relay response
checkpoint handling; transport, authentication, and other permanent failures
remain governed by the existing provider policy.

## Native capability assessment

- Existing owner and inspected files/symbols: `semantica/semantic_extract/providers.py::BaseProvider.generate_typed`; durable relay owner `semantica/semantic_artifact_builder.py::_ProjectModelProvider.generate` and `reject_last`.
- Actual callers / config / exports / tests / recent removals checked: `_product_json` passes `max_retries=3`; `tests/test_semantic_artifact.py` covers citation repair; `project_checkpoint.py` rejection markers were inspected.
- Decision: repair native owner.
- Evidence no second implementation is introduced: retry policy remains in `BaseProvider`; the hook only delegates durable rejection to the existing `_ProjectModelProvider.reject_last`.

## Approach and actual changes

- Changed `BaseProvider` to invoke an optional native rejection hook after validation or retryable generation failure.
- Reset `_ProjectModelProvider.last_checkpoint_entry` at the start of every generation and clear it after rejection, preventing stale successful entries from being rejected after transport errors.
- Added a regression test proving an invalid cached relay response is rejected and the next attempt makes a fresh relay call.
- No contract, stored-data, or model selection changes.

## Verification and limitations

- Planned: run the focused semantic artifact tests and native provider tests; publish a new immutable worker artifact and validate the packaged ESG build.
- Checks not run: full suite and packaged build not yet run.
- Known risks / unresolved questions: none identified in the focused path; release artifact must include this commit before production verification.

## Upstream merge assessment

- Disposition: pending.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: upstream may change the provider retry loop; re-evaluate the hook and preserve one retry owner.
- Required consumer/regression checks after merge: rerun the checkpoint regression and a packaged source-classification build.

## Dated follow-ups

No follow-up yet.
