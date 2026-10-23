# Isolate invalid model output and retain safe build warnings

- Record ID: 2026-10-23-local-extraction-warnings
- Date / author: 2026-10-23 / OntoScience maintainers
- Status: implemented locally; publication pending
- Fork base revision: def24279a22c8efe1121ec2685844187eb06d95d
- Upstream reference: not inspected; local fork main inspected
- Related issue / PR / commits / records: ESG build b50b4ee3-7120-4661-ba0f-97262f67d373

## Reason and scope

A single extraction task currently aborts the project. Its parallel-task diagnostic
also hides causal schema validation details. Invalid model output is local to the
extraction operation; authentication, exhausted transport retries, artifact and
grounding invariants must still fail closed. No quota accounting or new extractor.

## Native capability assessment

- Owners inspected: semantic_artifact_builder._ProjectModelProvider,
  _extract_project_sources; semantic_extract.grounded_window; semantic_worker._response.
- Callers/tests: native entity/relation methods, checkpoint cache, parallel scheduler,
  test_semantic_artifact_scheduling and test_semantic_worker_validation_diagnostics.
- Decision: repair native owners; retain the existing extraction and progress chain.
- No second implementation: native extractors and model receipts remain authoritative.

## Approach and actual changes

- Introduce a typed local model-output defect, preserve valid entities if only
  relations fail, emit source/window/page-bound warning events for rejected output.
- Merge safe causal validation/fault details with existing parallel context.
- Consumer impact: new optional progress metadata; no artifact schema migration.
- No new dependencies or network calls; native retries remain bounded.
- Implemented: typed local model-output isolation, candidate-local entity/relation
  rejection, safe causal diagnostics, source/window warning metadata, and page
  overlap guards for missing Docling offsets. Packaged publication and real ESG
  acceptance remain pending.

## Verification and limitations

- Red regressions ran before the source changes (2 failed, 1 passed). After the
  changes, 13 focused Semantica tests passed, including malformed relations and
  page mapping with missing offsets. OntoScience daemon warning/worker tests
  passed: 52 tests in 2 files.
- No historical raw invalid response was retained; do not claim its exact cause.
- Warning journal persistence belongs to the host; unknown pages remain unknown.

## Upstream merge assessment

- Disposition: pending; adapt if upstream offers equivalent typed local isolation.
- Incoming upstream revision: not yet reviewed.
- Overlap: grounded_window, provider relay validation, worker diagnostic response.
- Retain while native extraction isolates model defects without hiding invariants.
- Required checks: scheduling, grounding, worker diagnostics, consumer journaling.

## Dated follow-ups

- 2026-10-23: record created before implementation.
- 2026-10-23: implementation and focused verification completed. Classification
  warning journaling and real package acceptance are still open.
