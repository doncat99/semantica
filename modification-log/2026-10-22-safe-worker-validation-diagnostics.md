# Safe semantic worker validation diagnostics

- Reason: the worker returned Pydantic validation failures as opaque exceptions, which hid the rejected protocol field path needed to diagnose the failed OntoScience build.
- Reused owner: the existing `SemanticArtifactBuildRequest` and extraction Pydantic schemas remain the validation owners; the worker only projects their field names into a safe diagnostic.
- Method: include bounded validation count, schema-known field locations, safe non-negative list indexes, and normalized Pydantic error types. Exclude input values, context, URLs, and original validation messages; replace the public error message with fixed text.
- Affected callers/data: `build_semantic_artifacts` worker error responses consumed by the OntoScience Semantica adapter. No persisted domain data or request behavior is changed.
- Verification: `tests/test_semantic_worker_validation_diagnostics.py` covers field-path visibility and exclusion of arbitrary input values; OntoScience adapter regression coverage is in `apps/daemon/tests/knowledgehub-semantica-worker.test.ts`. Runtime/release acceptance remains pending a pinned CI-built bundle.
- Upstream merge implications: source change is on the user fork only; do not change upstream. The GitHub Actions native release workflow must build and publish immutable wheel and platform bundles before OntoScience can pin or package this behavior.
