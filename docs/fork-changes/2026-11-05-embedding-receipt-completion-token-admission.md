# Admit real embedding receipt usage without changing its evidence

- Record ID: 2026-11-05-embedding-receipt-completion-token-admission
- Date / author: 2026-11-05 / Codex
- Status: verified-in-stated-scope
- Fork base revision: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
- Upstream reference: not inspected; local current owner inspected
- Related records: `2026-11-05-native-builder-fact-membership.md`

## Reason and scope

Real embedding responses included `usage: {prompt_tokens: 7,
completion_tokens: 0, total_tokens: 7}`. The model execution and accepted
result succeeded, but native vector adoption rejected the extra usage key.
This prevented vectors and their receipt from entering the sole native store.

## Native capability assessment

- Native owner: `SQLiteVecStore.adopt_embedding` in
  `semantica/vector_store/sqlite_vec_store.py`. It validates and atomically
  persists vectors plus the exact serialized receipt.
- Producer: `semantic_artifact_builder._request_embedding` copies the response
  usage into `ModelReceipt.metadata` without filtering. `ModelReceipt.metadata`
  is an open dictionary in `semantic_artifact_schema.py`.
- Host relay inspected: `apps/daemon/src/model-gateway.ts` requires provider
  input/output usage and emits embedding usage with prompt and total counts.
  The native store accepts the additional real provider zero-completion field.
- Callers/tests: native builder and vector adoption/restart tests. Decision:
  repair the native validator; no second adapter or receipt rewrite.

## Approach and actual changes

- Permit `completion_tokens` in embedding usage only when it is zero. Require
  the total to equal prompt/input tokens when both are present. Preserve the
  exact usage dictionary in the persisted receipt and its digest.
- Invalid nonzero generation counts, negative counts and inconsistent totals
  still fail before vector writes. The accepted paid result remains available
  for explicit recovery; no live ESG database was changed in this patch.
- No model calls, dependency changes or data migration.
- Planned but not implemented: final fixed-artifact ESG build and publication
  lifecycle are separate G4 acceptance work.

## Verification and limitations

- Red specification first: four new vector tests yielded one failure for the
  real zero-completion receipt and three expected passes for invalid usage.
- `pytest tests/vector_store/test_embedding_handoff.py
  tests/test_native_embedding_builder.py
  tests/test_native_embedding_residency.py -q`: 32 passed in 17.89 seconds.
- `git diff --check` on edited source/test: passed.
- Full fork suite, installed artifact and real ESG rerun are not claimed.

## Upstream merge assessment

- Disposition: keep until upstream native adoption accepts valid provider
  embedding usage while preserving receipt integrity.
- Incoming upstream revision reviewed: none.
- Likely overlap: `SQLiteVecStore.adopt_embedding` receipt validation.
- After merge, rerun receipt roundtrip, invalid-usage, restart and builder
  tests; drop this change if upstream covers the same contract.

## Dated follow-ups

- 2026-11-05: Initial repair and scoped verification recorded.
