# Bound classification body retention in its existing batching owner

- Record ID: 2026-11-04-classification-body-batches
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus shared working changes
- Upstream reference: not inspected
- Related records: 2026-11-04-build-evidence-references.md

## Reason and native capability assessment

The existing `_classify_source` consumed all reference quotes into a list, and
`_context_batches` retained every resulting body batch. These are the native
classification owners in `semantic_artifact_builder.py`; no replacement owner or
external algorithm is needed. Inspected all calls to `_context_batches` (only
classification in production), classification reduction and long-context tests.

## Actual changes

`_context_batches` yields the same greedy batches from an iterable and retains
only the current batch and lookahead. `_classify_source` hydrates passages lazily.
A bounded preflight traversal preserves rejection of any oversized record before
any model request; it then traverses the references again for execution. Fixed and
indivisible budget failures now carry `MODEL_CONTEXT_BUDGET_EXCEEDED`, nonretryable.
The existing reduction, all evidence IDs, prompts, decisions and receipts remain
unchanged. No schema, persisted-data, dependency, export or pin change.

Preflight adds one local reference-hydration traversal; no additional model or
network requests. This is deliberate to preserve the old eager validation boundary
without retaining the complete source body.

## Verification and limitations

- Red specification: new lazy-consumption test consumed all 20 records before the
  first batch; classification retained all 20 quote objects at the first request.
  The late oversized error had no typed code. All three reproduced before repair.
- `pytest -q tests/test_classification_body_budget.py tests/test_native_reduction_boundaries.py tests/test_semantic_artifact_long_context.py`: 33 passed.
- `pytest -q tests/test_semantic_artifact.py tests/test_native_build_pipeline.py tests/test_native_build_lifecycle.py tests/test_native_producer_publication.py tests/test_native_global_body_budget.py tests/test_native_build_body_budget.py`: 45 passed.
- The weak-reference oracle admits at most three live quotes for a one-record
  batch, checks complete evidence order, and requires preflight before requests.
  Existing long-context coverage proves complete 90-passage classification.
- This closes classification batch-body retention only. Source references,
  assignments and receipts still scale with required output. Full parsed-source
  loads, entity contexts, global candidate/topology arrays, and a large individual
  span remain G4 gaps. No full-project RSS, immutable artifact or real ESG/release
  acceptance is claimed.

## Upstream merge assessment

Pending: incoming upstream revision not inspected. Recheck the builder's single
classification path and preserve greedy batch coverage, complete serialized budget
checks, preflight before paid work, and native classification reduction. Drop this
patch if the upstream owner already provides those guarantees with bounded bodies.
