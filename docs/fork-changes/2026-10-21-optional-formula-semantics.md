# Optional source-scoped formula semantics

- Record ID: 2026-10-21-optional-formula-semantics
- Date / author: 2026-10-21 / OntoScience
- Status: implemented; focused verification passed, release and App verification pending
- Fork base revision: bc749b35452f5a8695bbde359c082f4f57b74cac
- Upstream reference: not inspected in this change
- Related records: 2026-10-19-snapshot-archive.md

## Reason and scope

Default structural formula locations must remain available without asking the model to produce semantic variable bindings for every PDF. Selected source IDs may explicitly opt into grounded formula, variable, unit, and applicability extraction. This does not guarantee complete bindings or introduce calculations.

## Native capability assessment

- Owner: `semantic_artifact_builder._extract_project_sources`, `semantic_extract.grounded_window.extract_grounded_window` and the existing strict entity/relation prompts in `semantic_extract.methods`.
- Callers/config/tests: `RecipeRef`, worker build request, checkpoint input fence, `tests/test_grounded_window.py`; the older `formula_bindings` draft was excluded from main.
- Decision: extend native extraction, not a second LLM pass, graph, or facts table. Existing evidence, entities and relations remain authoritative.

## Approach and actual changes

- `formulaSemanticsSourceIds` is an optional, validated recipe field, empty by default. Only selected sources add formula-focused guidance to the existing model calls. Recipe and checkpoint digests bind selection to output; model receipts continue to account for actual calls.
- Basic Docling formula recognition and located structural evidence remain unchanged. No complete formula-binding storage is added.
- OntoScience must expose explicit selection and update its immutable release pin before installed Apps can use this option.

## Verification and limitations

- Red spec: `pytest -q tests/test_grounded_window.py -k formula_semantics_is_explicit` failed with missing option before implementation.
- Focused regression: 39 passed across grounded extraction and artifact contracts after the default-recipe compatibility fix. A separate cache test confirms disabled calls reuse the previous extraction result while enabling the option changes the prompt and cache key without an additional model pass. The disabled recipe keeps its previous serialized shape in checkpoint and lineage digests. Real PDF quality and packaged App verification pending.
- Expanded native-reduction suite: 53 passed, one existing fixture fails because it omits required `confidence` and `attributes` from its simulated entity response. This fixture failure does not qualify as a full-suite pass.
- Same-source cross-page binding is bounded by the existing window extraction; missing or conflicting definitions are not invented. Existing extraction failures retain their current build semantics; no new independent semantic phase exists.

## Upstream merge assessment

- Disposition: pending; upstream revision not inspected. Compare native grounded extraction and recipe schema before merging. Keep only while upstream lacks source-scoped optional formula guidance, and rerun worker, checkpoint and grounding tests.

## Dated follow-ups

- 2026-10-21: source-scoped recipe option implemented; verification and publication are separate steps.
