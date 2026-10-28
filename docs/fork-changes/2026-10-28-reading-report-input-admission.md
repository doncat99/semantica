# Reading report knowledge input admission

- Record ID: 2026-10-28-reading-report-input-admission
- Date / author: 2026-10-28 / Codex
- Status: implemented; focused and relocated native verification passed, App packaging in progress
- Fork base revision: a6900100d25b51990cbebee1b28b7fafc9f7b7b9
- Upstream reference: not inspected; fork-native repair
- Related issue / PR / commits / records: OntoScience Knowledge Research Summary failure

## Reason and scope

Summary repeated complete entity evidence indexes on each quote, and included
every source passage as well as extracted evidence. A ten-byte quote expanded
to over 400 KB and failed local report admission. Keep full provenance in the
snapshot, admit canonical qualified knowledge and representative grounding to
reading reports. Explicit source-evidence explanations retain caller scope.

## Native capability assessment

- Owner: semantic_artifact_builder.py::_explanation_reports / _grounded_explanation;
  kg/community_summarizer.py::CommunitySummarizer.summarize_evidence.
- Callers: semantic_worker.py::_reading_reports / _explain_evidence;
  OntoScience reading-report-generation.ts and runtime.ts.
- Existing fact reconciliation owns semantic identity; input admission must not
  introduce a competing scorer, fact reconciler, model path or host generator.
- Tests: test_semantic_artifact.py, test_semantic_artifact_long_context.py,
  test_semantic_artifact_grounding_budget.py.
- Decision: repair native report input construction and retain native packer,
  budget checks, structured generation and batch-isolated citation validation.

## Approach and actual changes

- Planned: select necessary grounding per canonical fact and representation;
  avoid parallel assertion/relation projections and repeated entity occurrences;
  keep source coverage without reading all raw passages again.
- Full snapshot and locator storage remain authoritative and unchanged.
- No new dependencies, model operation, budget increase or network fallback.

Implemented in the native owner: Overview reuses CommunitySummarizer's native
degree-centrality ranking and admits four subject/predicate proposition families
per source. All values/qualifiers/statuses in admitted families and all
contradicted/retracted/rejected families remain together. Detailed target reports
retain their scoped facts. Entity endpoint names are included without occurrence
arrays; duplicate assertion/edge projections share grounding. One normal support
per representation is retained, along with all distinct structural support quotes.
Uncovered overview sources receive one representative passage; scoped reports do
not expand to other sources merely because an endpoint was mentioned there.

## Verification and limitations

- Focused native admission/artifact/context/budget tests: 69 passed, one known
  baseline retry-count assertion deselected (details below). Contract/query/worker
  diagnostics/community tests: 126 passed. Host reading-report scope/runtime/
  projection regression: 39 passed. Host guard and typecheck passed.
- Built inventoried local development artifact
  `sha256:0bf5f8af85e456b4f8b374351fc40db920ecba8d74a1da148b60a5ae071e95ef`.
  Isolated installed-artifact acceptance passed: parsers/OCR, fresh build/query
  workers, loopback typed model generation, citation receipts and post-run
  inventory. This is not real-provider prose-quality acceptance.
- Host change-verification run e3cbd43b-902b-4cbe-9e62-c95694d891a7:
  22 UI tests passed, one failed, five not run. Failure: Summary evidence
  navigation omitted expected `match=lines%3A4-5`; outside native admission.
  Existing capability-knowledge-summary / page-knowledge-summary cases kept;
  native regression is supporting evidence, no acceptance baseline promoted.
- Packaged consumer integration pending.

2026-10-28 real-data dry run on the saved 38-source ESG snapshot
5c91a148a93f791a (mocked typed provider, no paid generation): 106158 stored
evidence spans / 14933 assertions / 14933 relations become 1561 admitted supports,
669 assertions and 32 nonduplicate relations; all 38 sources represented.
Context JSON is 894836 UTF-8 bytes. Native packing produces six requests,
951653 total prompt bytes, largest prompt 166366 bytes. Merely compacting all
facts still required 72 requests / 13578940 prompt bytes, so that intermediate
approach was not sufficient. Existing model and context/output budgets unchanged.

Known baseline failure: test_native_report_cannot_introduce_evidence_from_another_batch
expects one attempt but typed generation retries three times. Reproduced with
the original HEAD _grounded_explanation loaded via AST, without modifying source.
Both baseline and repair reject the invalid citation. This change does not alter
provider retry policy or weaken that test.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Reconcile against native builder/report packer changes and retain a single
  input owner. Re-run payload, grounding, scope and worker regressions.

## Dated follow-ups

- 2026-10-28: corrected the overview-only default introduced by the earlier
  budget repair. Inspected revision 823048f; native owners remain
  `_explanation_reports` and worker `_reading_reports`. The native default plan
  now selects overview, up to six evidence-backed topics and six grounded core
  concepts using CommunitySummarizer's existing centrality implementation.
  This bounds initial reading scope; it is not a context-window increase or
  exhaustive generation for all entities. Explicit scopes remain supported.
  The worker accepts existing same-snapshot target IDs, returns plannedTargetIds,
  and skips saved reports without calling a model. Host publication checks that
  the complete plan is present after merging saved reports. Admission suite:
  10 passed, including bounded grounding and no-paid-call reuse regressions.
  Packaged real-data verification for this correction is pending. No change
  to budgets, citation validation, retries or upstream merge disposition.

- 2026-10-28: run 3f6bc786-5f48-4c73-9497-d4f69deac804 classified 39
  rejected citations as citation_unknown_evidence. Native _grounded_explanation
  now exposes request-local e1/e2 references instead of long storage identities,
  keeps native per-batch strict validation, and maps validated references back
  before sections/checkpoint publication. No fuzzy matching, grounding relaxation
  or budget increase. The payload/remapping regression failed before this fix;
  checkpoint and source-scope fixtures now reflect the model-facing contract.
  Real-provider acceptance pending. Same native owner/revision as above.

- 2026-10-28: real run 997159fd-fe9f-4d94-903c-b450c8fe47e5 rejected
  41 citations with indistinguishable value_error diagnostics. The existing
  _SemanticCitation owner now emits safe typed reasons for unknown evidence,
  missing canonical quotes and quote mismatches, without emitting input values
  or changing admission. Three red diagnostic regressions now pass, along with
  the existing reading-report admission tests (12 passed). Actual cause and
  real-provider acceptance remain pending; inspected fork revision 823048f.

- 2026-10-28: record started before implementation.
- 2026-10-28: packaged real-provider run b3859b5d-6ebf-4dc6-a791-6d3c04dbb6e4
  passed budget admission but failed typed-output validation. Inspection found
  findings were declared as arbitrary dictionaries in the wire schema while a
  private validator required summary, explanation and grounded citations. Added
  a red wire-schema regression, declared the existing _GroundedFinding type,
  and serialized nested findings at CommunitySummarizer's native report boundary.
  No schema or citation checks were relaxed. Exact rejected provider fields were
  not retained by the host run cleanup; this is a proven contract defect, not
  a claim that the discarded response was inspected. Focused owner/context/
  grounding/admission suite: 67 passed, one known baseline test deselected.
- 2026-10-28: native `semantic_worker._response` now reuses `model_output_cause`
  to retain the existing safe typed-output diagnostic through ProcessingError.
  The regression first returned INTERNAL_ERROR without schema paths; it now
  returns MODEL_OUTPUT_SCHEMA_INVALID and the missing-field diagnostic without
  provider input values. Combined native artifact/admission/context/grounding/
  worker/PDF ownership selection: 92 passed, one documented baseline retry-count
  assertion deselected. No retry policy, citation validation or budget changed.
- 2026-10-28: packaged artifact sha256:2829e85b166f01f7965aa4d6a3dc2532071b9a127e97795847b09907b150c3cb
  completed real-provider report run 5b0858e9-49d7-4c5b-8d22-6d2ea5e70c2d.
  Report published against the existing adopted 38-source snapshot; 40 sections,
  five model receipts, 218544 prompt tokens and 11588 completion tokens total.
  No context/output budget increase (500000/32768) or grounding relaxation.
  Native focused suite: 140 passed, one independently reproduced baseline
  retry-count assertion deselected. Actual App rendered report prose and source
  citation controls. Source preview opened; exact page/line navigation remains
  a separate host acceptance gap. Report success does not certify all research
  output quality or host Auto Test cases.
### Scope admission correction, 2026-10-28

Real adopted 38-source snapshot inspection showed that bounded target counts alone
still selected 8,104 facts for one topic and 1,267 for one concept. The existing
native `_overview_knowledge` admission now also applies inside topic/concept scopes:
four central proposition families per source with complete qualifiers, variants,
and conflict families. The canonical snapshot remains exhaustive. A regression
first reproduced both scoped reports sending all 100 fixture facts. Packaged
verification is pending; this is not a claim of real-provider acceptance.
