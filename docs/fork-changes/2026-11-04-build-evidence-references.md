# Build evidence references reuse the native range reader

- Record ID: 2026-11-04-build-evidence-references
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus existing shared working changes
- Upstream reference: not inspected in this follow-up
- Related records: 2026-11-04-source-range-hydration.md; 2026-11-04-native-build-body-budget.md

## Reason and native owner assessment

`semantic_artifact_builder.source_processing` released parsed documents but kept
all EvidenceSpan/passages quote bodies across all sources. Existing native owner
`semantic_document_reader` already owns scalar-addressed reads of the sole parsed
artifact. Reuse that reader; no extraction store API or second quote store is needed.
Inspected `_source_passages`, `_build_source`, classification/report consumers,
source relations, organization, topic publication and index publication. Existing
extraction records already retain native ranges under per-operation budgets.

## Actual changes

The builder projects each accepted span to transient identity/locator/metadata,
length and digest. Neither quote field is retained. Hydration delegates to the
current native range reader and verifies exact length/digest; it does not cache
the body. Classification, report citations and their content hashes keep their
existing values. Organization and native publication consume locator metadata
without hydrating source text. The common installed-reader request constructor is
also reused by index publication. No protocol, persisted data, dependency or pin
changes; no network/model requests are added by hydration.

## Verification and limits

- Before this cut, the global lifetime regression reproduced retention of 4,104
  original deterministic spans and 1,032 model spans.
- `pytest -q tests/test_native_producer_publication.py tests/test_native_build_pipeline.py tests/test_native_build_lifecycle.py tests/test_native_embedding_builder.py tests/test_native_embedding_residency.py tests/test_organization_report_product.py tests/test_no_checkpoint_runtime.py tests/test_native_extraction_handoff.py tests/test_semantic_artifact_native_extraction.py tests/test_semantic_artifact_grounding_budget.py`: 78 passed.
- Global regression is strengthened to require zero original spans and complete
  ID/quote/locator/metadata digest equivalence on two hydration traversals.
- This does **not** complete G4. `_load_parsed_source` still loads one whole
  parsed JSON. Entity context and complete candidate/topology arrays remain.
  A very large single evidence span or report context can still allocate its
  full selected body; range-read bounds alone do not prove a global RSS bound.
- No immutable artifact, host acceptance, real ESG execution or release was run.

### 2026-11-04 follow-up verification

`test_native_evidence_reference.py`, `test_native_global_body_budget.py` and
`test_native_build_body_budget.py`: 9 passed. Both full quote traversals preserve
the complete ID/quote/locator/metadata oracle while no original EvidenceSpan
survives globally. Multi-window Unicode and page separators are exact; artifact
or index mutation after a successful read and accepted quote-digest disagreement
are rejected. The unchanged host reader cross-repository test was rerun against
this native source: 2 passed (explicit source test, not installed-artifact proof).
Classification's eager quote batching is separately repaired and verified in
`2026-11-04-classification-body-batches.md`. Single-source full loads, context and
structural metadata bodies, global candidates/topology and individual large
span/report hydration remain outside this cut's resource guarantee. G4 is not
complete.

## Upstream merge assessment

Pending; incoming upstream revision not reviewed. Reassess the native builder and
reader together, preserving exact offsets, content hashes, cancellation and
candidate coverage. Drop this transient projection if the native builder no longer
retains aggregate evidence bodies; do not preserve a compatibility reader.
