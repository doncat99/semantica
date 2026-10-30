# Classification model evidence references

- Date: 2026-10-31
- Status: verified in focused scope; packaged acceptance pending
- Fork base revision: bcf24a641fb8d271ac55725ebd979b7fdd958e3a
- Upstream reference: not refreshed; upstream merge assessment pending

## Reason and native capability assessment

Packaged ESG runs 6f584b4a-835c-4ae5-b1b6-0e8432ffbabe and
3baadbad-d185-429f-a887-dc5735ea7378 failed source classification.
The model combined adjacent canonical evidence offsets into an unsupplied ID.
Native `_SemanticCitation` correctly rejected it; three typed retries in the
second run all failed. A parsing/extraction reuse event is not warm acceptance.

Inspected existing owners in semantic_artifact_builder.py: `_classify_source`,
`_classify_source_batch`, `_product_json`, `_grounded_explanation`,
`_SemanticCitation`; native BaseProvider.generate_typed owns repair attempts.
Reports already use short model references with strict canonical restoration.
Repair classification by reusing this boundary, not a new classifier or retry
owner. Tests test_semantic_artifact.py and test_semantic_artifact_long_context.py
exercise actual classification, typed provider, checkpoint and report callers.

## Actual changes

Extract the report's existing evidence-reference projection into
`_model_evidence_context`. Classification uses e1/e2 references in model input,
validates against exactly that supplied set, maps accepted citations to canonical
IDs, validates again and persists only canonical results. Existing successful
product-result identity and restoration are unchanged. No extra knowledge store,
fallback, fuzzy matching, rejected-output admission, dependency, retry expansion
or paid-cache deletion. Unfinished classifications need new requests; successful
canonical results remain reusable. Model determinism remains outside our control.

## Verification

The short-reference regression failed on the prior implementation. Focused run:
138 passed, 2 deselected across test_semantic_artifact.py,
test_semantic_artifact_long_context.py, test_project_identity.py,
test_semantic_artifact_native_extraction.py and
semantic_extract/test_grounded_llm_extraction.py. The two excluded existing
long-context failures were reproduced using HEAD's pre-change builder:
long_extraction_visits_tail expects one support per entity;
native_report_cannot_introduce expects one attempt despite native three retries.
They are not passing evidence. New regression checks canonical persistence and
zero additional model calls on checkpoint restoration. Real successful build and
warm rebuild remain pending; no zero-token production claim is made.

## Upstream merge assessment

Pending incoming upstream review. Preserve one evidence-reference projection and
native typed validation/retry owner. Adapt or remove this extension if upstream
provides the same citation contract. Re-run classification, report, checkpoint
and real packaged warm acceptance after any merge.
