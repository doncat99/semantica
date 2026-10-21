# Worker resource lifecycle

- Record ID: 2026-10-20-worker-resource-lifecycle
- Date / author: 2026-10-20 / OntoScience maintainers
- Status: implemented; focused validation complete; upstream assessment pending
- Fork base revision: 87b8bb8fd356ddb6a0c5ada3cdeb99fed2f1ed4d
- Upstream reference: not inspected for this change
- Related records: OntoScience resource-lifecycle-execution.md, R1–R3/R11

## Reason and scope

The published worker takes 11.243 seconds for a cold schema request versus
13.641 milliseconds in the same process. This is evidence of startup cost,
not a measurement of PDF binding or complete build latency.

## Native capability assessment

- Owner: semantic_worker.py::serve already accepts successive JSONL requests.
- semantic_artifact_builder.py owns parse/bind and error types, but importing it
  eagerly loads extraction, entity resolution and pipeline dependencies.
- source.py and parse/docling_parser.py remain the sole native parse owners.
- Callers/tests inspected: semantic worker dispatch, native grounded source,
  semantic artifact contract and project document quality tests.
- Decision: move the existing source-artifact implementation into a lightweight
  native module, reexport from the builder, and defer heavy worker imports.
  No duplicate parsing, identity, quality or provenance implementation is added.

## Approach and actual changes

- Planned: lazy worker imports; shared lightweight errors/source artifact owner;
  cold-process regression tests and existing native regression replay.
- Stored protocols, source identities and quality admission remain unchanged.
- Source implementation moves must participate in checkpoint recipe digests.
- No network/model calls, new dependency or consumer checkout fallback.
- Worker pooling/converter lifetime and relay transport remain separate work.

## Verification and limitations

- Focused fork validation on 2026-10-20: 60 tests passed across
  `test_docling_lifecycle.py`, `test_semantic_worker_imports.py`,
  `test_native_grounded_source.py`, `test_semantic_artifact.py`, and
  `test_project_source.py`.
- The complete `test_docling_parser.py` suite is not verified in this checkout:
  12 tests fail because `docling_core` is absent from its Python environment,
  leaving the optional Docling imports unavailable. Do not treat those failures
  as proof of a source regression or as successful parser validation.
- `uv run pytest` did not reach pytest after more than two minutes spent
  normalizing existing invalid dependency specifiers; direct `.venv/bin/pytest`
  was used for the focused tests instead.
- No immutable release or OntoScience packaged acceptance is claimed.

## Upstream merge assessment

- Disposition: pending; upstream revision not reviewed.
- Likely overlaps: worker dispatch, builder source functions and parser imports.
- Retain one native implementation; rerun source, checkpoint, protocol and PDF
  ownership tests after merges. Adapt/drop if upstream supplies equivalent owners.

## Dated follow-ups

- 2026-10-21: publication review against `87b8bb8f` confirmed that these
  changes move the existing parsed-source implementation, preserve its builder
  reexports, and retain native PDF/Docling ownership. No replacement semantic
  algorithm or additional model call is introduced. The converter lease is
  serialized, retains only the latest configuration, and discards failed state.
  Request credentials are excluded from serialization and reset in `finally`.
  The remote profile no longer accepts `authorizationEnv`: remote consumers
  must pass `documentProcessingAuthorization` on the worker request or install
  the request-local context when calling the native adapter directly. This is
  an explicit consumer contract migration, not an environment fallback.
- 2026-10-21: `.venv/bin/pytest -q` passed 98 tests across Docling lifecycle,
  worker cold imports, grounded source, semantic artifacts, project source,
  document quality, remote Docling and PDF reader ownership. A second run of
  artifact-contract/query-worker/parser suites passed 57 tests and reproduced
  12 parser failures caused by missing `docling_core` in that Python 3.12
  environment. All 21 parser/lifecycle tests then passed in the ESG Python
  3.13 semantic environment with installed Docling dependencies (6.83 seconds,
  one OCR deprecation warning). That environment has no pytest; the invocation
  appended the fork test environment's site-packages for the pytest runner,
  with plugin autoload disabled. No environment was installed or modified.
  `git diff --check` passed. These are focused checks, not full-repository,
  real-document throughput, consumer deployment or sustained-run acceptance.
- 2026-10-21: rollback is a main-branch revert plus a consumer package rollback;
  coordinate the remote credential request contract on rollback. Original
  source bytes are unchanged. Checkpoint recipe identity includes the moved
  source implementation and authorization context, so old recipe checkpoints
  are not silently reused. No upstream merge was attempted or qualified.

- 2026-10-20: initial native-owner review and planned changes recorded.
- 2026-10-20: lazy worker import isolation and shared Docling parser lifecycle
  focused tests passed (60 fork tests total across the listed suites). Full
  Docling parser validation remains blocked by missing `docling_core`; no fork
  commit, publication, or consumer pin was performed.
- 2026-10-20: remote Docling authorization is request-scoped, not an
  environment configuration. `DocumentProcessingProfile` contains only mode,
  endpoint, binding ID and cancellation behavior. The worker transports the
  credential in its private request field, installs it in a `ContextVar` for
  that request, and resets it in `finally`; parser launch environments and
  durable profiles do not contain the credential. Regression tests cover
  sequential credential isolation, legacy environment fallback rejection,
  profile schema rejection and serialization redaction. `pytest -q
  tests/test_project_remote_docling.py tests/test_semantic_worker_imports.py`
  passed (9 tests); `ruff check tests/test_project_remote_docling.py` passed.
  A wider ruff invocation still reports three existing unused-variable errors in
  `project_remote_docling.py` and `semantic_artifact_schema.py`; those are
  outside this credential change and were not modified.
