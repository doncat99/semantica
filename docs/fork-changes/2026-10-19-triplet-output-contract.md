# Triplet structured output contract

## Reason and native ownership

Inspected revision f69d598466e7877a795b1bbccd35231910858558 (with existing unrelated local changes).
`semantic_extract/schemas.py:TripletOut/TripletsResponse` owns the wire schema;
`semantic_extract/methods.py:extract_triplets_llm` passes it to `generate_typed`.
The method constructs provenance locally and never consumes model metadata.
The existing unbounded metadata dictionary cannot be constrained by strict
OpenAI JSON Schema. Confidence also silently replaces invalid values with 0.9.

## Approach and affected callers

Keep one native TripletOut owner. Mark local-only metadata as absent from the
generation schema, retain its Python attribute for library consumers, and make
confidence a required bounded number without score repair. ESG's existing
gateway adapter translates this schema with the installed OpenAI SDK; no
second extraction or schema-generation algorithm is introduced.

## Regression and status

Planned: SDK schema compatibility, strict invalid-confidence rejection, native
triplet extraction tests and ESG transport tests. Results will be appended.
No deployment or real-provider qualification is established by this record.

### 2026-10-19 verification

Implemented in the existing schema owner. Native focused tests
`tests/semantic_extract/test_triplet_wire_contract.py` and
`tests/semantic_extract/test_structured_output.py`: **13 passed**, no skips,
using ESG's isolated Python 3.13 runtime with OpenAI SDK 3.26.0 and Pydantic 2.13.5.
The original schema reproduced the strict-contract failure because metadata
appeared as an unbounded model-generated object. The new tests check SDK schema
closure, required bounded confidence, retention of local metadata and rejection
of malformed confidence without repair.

ESG's clean candidate wheel was also exercised by all four actual semantic
business callers with captured SDK request arguments. Its 435 Python modules
were compared with the previously qualified installed distribution: only
`semantic_extract/schemas.py` differs, and the existing PDF change is preserved.
Unrelated dirty identity work was excluded. Candidate wheel SHA256:
`af59485da0f61583c7e30bf131fca357d675a7f61376abc782b524314c3f1419`.
ESG integrated caller/gateway/browser/Review/Jev/recovery regression: 305 passed;
actual Bifrost protocol with local upstream: 1 passed. Neither is a paid-provider
or production deployment qualification. Detailed consumer evidence and command
scope are in ESG's `docs/audits/2026-10-19-structured-output-contract-review.md`.
Standalone native provider implementations outside the registered ESG gateway
were not changed or certified by this work.

## Upstream merge assessment

Adapt if upstream separates model output from locally constructed provenance;
drop this change when that native contract supersedes it. Python metadata stays
available, but applications requesting metadata from model output must migrate
to an explicitly typed schema. Required confidence is an intentional wire change.
