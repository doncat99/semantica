# Validate explanation checkpoints before reuse and persist native reports

- Record ID: 2026-10-27-explanation-checkpoint-admission
- Date / author: 2026-10-27 / OntoScience contributors
- Status: verified-in-stated-scope
- Fork base revision: d44dd1583a57df34854a3b2300e81f8c4cde37d4
- Upstream reference: not inspected in this repair
- Related commits: 183f56f78, c4b0ed444, d44dd1583 (preceding relay and product checkpoint repairs)

## Reason and scope

ESG builds reported MODEL_OUTPUT_SCHEMA_INVALID after protocol alignment. The preceding
repairs rejected invalid relay/product checkpoints; review found the explanation path
still validated saved model output outside generation recovery. Native CommunityReport
is a dataclass, but saving it called a nonexistent model_dump method.

## Native capability assessment

- Owner: semantic_artifact_builder.py::_grounded_explanation; kg/community_summarizer.py::CommunityReport.
- Callers: product explanation production; existing explanation tests and project checkpoint recovery tests.
- Reused SnapshotCheckpoint.reject and native typed generation retry. No alternate generator,
  prompt owner, fallback, cache implementation or protocol field is introduced.

## Approach and actual changes

- Reject only schema-invalid saved explanation results, then use existing generation.
- Convert native dataclass reports with asdict, validate using the existing grounded schema,
  and save its JSON representation. Keep receipts and valid cached outputs intact.
- Regression uses a real checkpoint, malformed/foreign citations, replacement persistence,
  and second-call reuse without another model request.
- Previously admitted source artifacts retain their strict integrity checks; this does not
  authorize discarding valid historical extraction or changing cache identity.
- Cost: one bounded regeneration only for rejected explanation output; valid reuse is unchanged.

## Verification and limitations

- New test failed before source repair on malformed saved citations; 9 focused tests passed
  in the original worktree after repair.
- Broader original-worktree run: 49 passed, 23 failed. Worktree contains unrelated staged
  schema removals that break native imports; PDF fixture dependency was also missing.
  Clean release-baseline run passed 70 tests; the two PDF fixture tests then passed using
  the pinned packaged worker's existing PyMuPDF on sys.path. Combined coverage: 72/72.
  Commands: pytest -q tests/test_semantic_artifact.py tests/test_project_checkpoint.py;
  pytest -q tests/test_project_checkpoint.py -k formula_requirement_change.
  This is supporting regression evidence, not full release acceptance.
- Packaged ESG build with preceding d44dd158 artifact is running; it excludes this follow-up.
- Acceptance mapping: OntoScience capability-library-prepare, primary owner journey-library,
  delta keep; existing recovery/grounding expectations and baselines remain unchanged.
- OntoScience guard (68 tests) and repository typecheck passed. Change-verification is running.

## Upstream merge assessment

- Disposition: pending; incoming upstream not reviewed.
- Recheck native report representation and typed checkpoint admission on upstream merge.
- Remove this repair only if the canonical owners provide equivalent behavior and these
  persistence/reuse regressions pass. Full packaged ESG acceptance remains required.
