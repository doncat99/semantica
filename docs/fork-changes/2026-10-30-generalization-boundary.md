# Keep contextual identity at the generalization boundary

- Record ID: 2026-10-30-generalization-boundary
- Date / author: 2026-10-30 / Codex
- Status: implemented-unverified
- Fork base revision: d0f7088490bca5b782d16549b3b00e45d97925b3, with prior uncommitted identity repairs preserved
- Upstream reference: not inspected this turn
- Related records: 2026-10-30-bounded-identity-resolution

## Reason and scope

The prior generic-body phrase rule enumerated body and complement words. That
does not meet the requested generalization boundary. Fix the ownership inference
that caused the false merge instead of extending the vocabulary to fit this corpus.
No entity-count target, additional extraction, production rebuild or host adoption.

## Native capability assessment

- Existing owner: `EntityDisambiguator` in `semantica/normalize/entity_normalizer.py`;
  `_dependent`, `_explicit_owner`, `_grounded_full_definition`, `_effective_owner`.
- Callers: native contextual `EntityResolver` / `DuplicateDetector`, invoked by
  `_resolve_native_entities` in `semantic_artifact_builder.py`. Existing grounded
  profiles, source-local owner reuse and independent institution handling retained.
- Decision: repair native owner, delete the phrase-specific helper. No second resolver.
- Tests exercise located source mentions through the project/native resolver path.

## Approach and actual changes

- Delete `_generic_body_name` and its body/complement enumeration.
- Reuse the existing dependent-head classification for the head of an `of` phrase;
  do not add lexical categories. A parenthetical expansion establishes a name,
  not necessarily an independently identifiable entity.
- Remove ownership guesses from `name of CapitalizedPhrase` and plain title
  adjacency. Retain grounded profile ownership (without requiring descriptions),
  explicit straight/curly possessives, and unambiguous local owner reuse.
- Independent institutional full names remain eligible for ordinary name matching.
- Processing version v8 -> v9 invalidates old processed identity results. Paid
  extraction contract/cache unchanged; checkpoint/local-reuse tests included.
- No model/network/dependency additions. Ambiguous input may stay unresolved;
  the resolver does not request additional evidence or drop mentions.
- Add generic positive/negative regression cases in
  `tests/kg/test_identity_review_regressions.py`.

## Verification and limitations

- Red specification before source repair: four failed, four passed (dependent
  complements and adjacency reproduced the bug). Focused seven-file suite after
  repair: 172 passed.
- Broad native suite: 1405 passed, 45 skipped, five subtests passed, 14 warnings,
  104.38 seconds. Offline replay exited zero: 36,082 mentions retained once,
  20,253 entities, zero network calls, 20.544s grounding / 184.583s identity.
- Replay exposed unresolved over-splitting: exact-name U.S. Department of Labor
  1 -> 7 groups and 2025 Corporate Impact Report 2 -> 78. Do not treat this repair
  as complete or ready for production rebuild. No new name exceptions added.
- Not a complete semantic accuracy adjudication. Existing lexical classification
  and English possessive recognition remain heuristic; do not extend them merely
  to reduce a particular corpus's group counts.
- No immutable release, host adoption, App rebuild, Summary acceptance, baseline
  change, production deletion or production rebuild performed.

## Upstream merge assessment

- Disposition: pending; incoming upstream not reviewed.
- Overlap: native normalizer and project processing version.
- Retain only while upstream lacks these invariants; adapt/drop if upstream owns them.
- After merge rerun contextual identity, grouping/veto, extraction, checkpoint/local
  reuse, and multi-family offline replay. Consumer product acceptance is separate.

## Dated follow-ups

- User subsequently requested physical reset of old results, not version bypass.
  Production deletion scope must be resolved separately; no deletion performed here.
