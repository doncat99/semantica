# Packaged model-path dependency and acceptance closure

- Date / author: 2026-10-23 / OntoScience maintainers
- Status: implemented-unverified
- Fork base revision: 0b40ed5828c2b3e5a796a3b64a7a3009bdc80a68
- Upstream reference: not inspected; this repairs fork-only worker delivery

## Reason and native capability assessment

The installed mac worker failed before its first relay call because
`semantic_artifact_builder._ProjectModelProvider.generate_typed` imports
`openai.lib._pydantic.to_strict_json_schema`, but worker extras omitted OpenAI.
The native owner was introduced by 287285811d71af452e9953bb88d884fb5d500079.
Inspected `pyproject.toml`, all six worker locks, `semantica/bundle.py`,
the native release workflow, `semantic_worker_acceptance.py`, and
`tests/test_semantic_artifact.py::test_model_recipe_uses_bifrost_chat_and_embedding_and_records_receipts`.
The existing acceptance only built the deterministic recipe and queried keywords.
Repair the native dependency/acceptance owners; no alternative extraction or
schema implementation is introduced.

## Approach and actual changes

- Declare the exact OpenAI SDK in `semantic-worker-common`, shared by CPU,
  CUDA and DirectML profiles; regenerate their immutable constraints.
- Extend relocated installed-artifact acceptance with a loopback-only mock
  relay and fresh isolated build/query workers. Exercise the real native typed
  entity/relation extraction, embeddings, classifications, grounded community
  explanation, keyword and vector retrieval; assert grounded results/receipts.
- Preserve deterministic parsing/OCR acceptance and post-run inventory checks.
- No production credentials, paid model requests or project data are used by
  these acceptance probes. No protocol or persisted-data migration.

## Verification and limitations

- Red regression: worker common-extra dependency specification fails on base.
- Installed-artifact red reproduction: model acceptance fails on base App with
  `No module named 'openai'` before any loopback request.
- Green focused regressions: 122 tests passed across release/bundle, native
  extraction, scheduling, query, artifact contracts, grounding and long context.
- The loopback model-path probe passed with the source environment: entity and
  relation extraction, embeddings, classification, explanation, keyword and
  semantic queries. This is not yet immutable installed-artifact evidence.
- All six resolved locks retain every previous package pin and add OpenAI plus
  its five missing transitive dependencies. Native platform results: pending.
- This offline gate establishes executable packaging paths, not real-model
  semantic quality or successful real ESG project completion.
- GPU hardware validation is outside this change; CPU platforms are release defaults.

## Upstream merge assessment

- Disposition: keep pending upstream equivalent dependency/worker acceptance.
- Incoming upstream revision: not reviewed.
- Reuse an upstream native owner if introduced; rerun isolated installed model
  paths and dependency specifications after merging. Do not replace native
  schema conversion with a second implementation.
