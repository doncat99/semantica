# Preserve native node types in Explorer

- Record ID: 2026-11-12-explorer-native-node-types
- Date / author: 2026-11-12 / Codex
- Status: implemented; native tests and artifact verified; App delivery blocked
- Fork base revision: be868dec59fa1f079f3c265ad578a4a321c092a0
- Upstream reference: not inspected
- Related issue / PR / commits / records: pending

## Reason and scope

Knowledge Map offered only Concept because NativeScope.select hardcoded the
top-level graph type, even though the scene supplied entityType. The installed
OntoScience Dev artifact contained the same hardcode. Preserve native types;
do not reclassify entities, rebuild user data, or change graph layout.

## Native capability assessment

- Existing owner: semantica/explorer/native_scope.py, NativeScope.select.
- Consumers: GraphSession, graph nodes API, Explorer useLoadGraph nodeTypes menu.
- Tests: tests/explorer/test_native_scope.py previously asserted the hardcode.
- Decision: repair native owner in place; no second implementation or fallback.

## Approach and actual changes

- Use the already-required entityType as the ContextGraph node type.
- Correct old assertions and cover mixed ORG/PERSON/Concept nodes through project,
  source, topic, community and explicit selection, including API type filtering.
- No stored-data migration/deletion: the Explorer graph is an ephemeral projection.
- No new dependencies, model calls, or network calls in the tests.
- Screenshot HTTP 422 is separate and not claimed fixed by this mapping.

## Verification and limitations

- Red: .venv/bin/python -m pytest tests/explorer/test_native_scope.py -q:
  7 failed, 11 passed; all failures expose flattened Concept types.
- Green: native scope/admission/API/entrypoint/auth suite, 191 passed twice.
- Rebuilt self-contained native artifact preserved Concept/ORG/PERSON through
  its own Python loader; full native release acceptance passed. Artifact digest:
  sha256:207435a05e62e5dc83255352e07abe02515ee762f39f0ae658fd7fd570f7246a.
- OntoScience make dev stopped at unrelated E2E reader typecheck (missing
  qualifyObjects/qualifyFact); installed Dev App remains unchanged.
- UI change-verification blocked before execution by concurrent source changes.
- No upstream merge or real-user UI acceptance yet.

## Upstream merge assessment

- Disposition: keep; retain native semantics while this projection exists.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping owner: NativeScope.select.
- After merge run native scope selection/API regressions; remove patch only if
  upstream preserves the same entity types in the canonical owner.

## Dated follow-ups

- 2026-11-12: red regression recorded before the source fix.
- 2026-11-12: green native suite and rebuilt artifact verified; delivery and
  real-user UI acceptance remain blocked, not passed.
