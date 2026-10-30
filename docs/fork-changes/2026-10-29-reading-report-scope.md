# Reading report scope and reader-specific explanation

- Record ID: 2026-10-29-reading-report-scope
- Date / author: 2026-10-29 / project contributors
- Status: implemented locally; consumer native artifact validation pending
- Fork base revision: ed2af3a561122827a9315343dcd8496175628df2
- Upstream reference: not inspected in this repair
- Related records: native reading report admission; host Knowledge Research Summary

## Reason and scope

Topic reports select every fact incident to any member entity, even when the
topic explicitly names a smaller assertion/evidence set. Shared entities therefore
pull unrelated knowledge into the explanation. Community reports similarly admit
boundary edges. Reader roles also share one generic instruction.

## Native capability assessment

- Owner: `semantica/semantic_artifact_builder.py::_explanation_reports`,
  `_reading_report_context`, `_grounded_explanation`.
- Callers: native `semantic_worker._reading_reports`; grounded report creation.
- Contracts: `KnowledgeTopic` has assertion/evidence membership;
  `KnowledgeCommunity` has entity/relation membership.
- Tests: `tests/test_reading_report_admission.py`, long-context and kernel regressions.
- Inspected history: `31396b842` already bounds reading selection; repair its scope
  admission rather than introducing another selector or model owner.
- Decision: repair native owner; retain CommunitySummarizer and its typed evidence validation.

## Approach and actual changes

- Respect topic assertion/evidence membership and community internal membership
  before the existing source-balanced admission. Clip topic evidence on copied
  records and reject boundary assertions, including legacy topic memberships.
- Explain overview, topic, community and concept according to their reader purpose;
  invalidate explanation checkpoints by recipe version. Do not reuse community
  prose as a topic explanation merely because title and members match.
- Keep extraction diagnostics out of research-question and source-dispute prose.
- No schema migration, alternate model path or new dependencies. Stored reports
  require explicit regeneration for new wording; host reference repair is separate.
- Expected cost impact: exclude unrelated supports before native batching.

## Verification and limitations

- Scope regressions were observed red before the source repair. Affected native
  report, long-context, reduction and kernel suite: 129 passed, 3 failed. All
  three failures were independently reproduced at the fork base: invalid-output
  retry-count expectation, typed-provider mock missing business_context, and
  extraction fixture without admitted relay budget. They are not repaired here.
- Native source changes alone do not update a consumer's immutable artifact pin.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Overlap: native explanation/report admission owner.
- Retain only while upstream lacks equivalent scoped admission; rerun report
  admission, typed grounding, long-context and worker tests after merge.

## Dated follow-ups

- 2026-10-29: recorded native ownership and planned repair before implementation.
- 2026-10-29: implemented explicit scope, role instructions and checkpoint versioning;
  verified existing baseline failures separately from the repair.
