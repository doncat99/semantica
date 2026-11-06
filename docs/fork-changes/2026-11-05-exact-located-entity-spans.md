# Exact native entity and identity-profile source spans

- Date: 2026-11-05
- Status: implemented; focused native regression verified, installed ESG recovery pending
- Inspected fork revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus current G4 working changes

## Reason and native capability assessment

Real HCA ESG extraction failed native adoption in `ExtractionRecords.write_entity`
after the model had returned HTTP 200. Native `_exact_occurrence` intentionally
locates source whitespace variants, but `extract_entities_llm` retained the model's
whitespace in `Entity.text` and profile evidence. Located offsets and payload thus
disagreed. The strict native writer correctly rejected the mismatch.

The existing owners are `semantic_extract.methods.extract_entities_llm` and
`triplet_store.extraction_records.ExtractionRecords.write_entity`. Consumers inspected:
`extract_grounded_window`, native adoption/hydration, publication window assembly
and `_build_source`. Repair the producer in place; preserve writer exactness.

## Implementation and affected consumers

After successful strict grounding, entity text and identity-profile evidence are
copied from their exact located source spans. Semantic description, owner, instance,
occurrence, attributes and original offsets remain intact. Non-strict extraction
is unchanged. No additional model call, schema, dependency or compatibility path.
Existing vectors have unchanged source-window text and embedding model inputs.

## Evidence and limitations

Four red specifications reproduced normalized model whitespace versus newline,
double-space, tab and nonbreaking-space source mentions. They then verify native
adoption/hydration and exact profile evidence with one typed provider call.
Host evidence: `.tmp/g4-exact-entity-red.log`, `.tmp/g4-exact-entity-green.log`.
Focused extractor, native extraction records and scalar grounding suites are the
verification scope. A separate existing grounded-window receipt fixture expects
removed `rejected_candidates` instead of `rejected_count`; this patch does not
change that owner or claim full-suite acceptance.

Previously failed accepted envelopes require explicit offline repair or rejection
under the current processing contract; this source change does not certify invalid
cached DTOs as successful native receipts. Previously adopted records have already
passed the unchanged writer's exact-source check. Installed artifact, paid-output
preservation and real ESG continuation remain integration acceptance work.

## Upstream merge assessment

Keep pending upstream assessment. No upstream revision reviewed. Preserve exact
native source spans, ambiguous-occurrence validation and single-call regression
coverage when merging future grounding changes.
