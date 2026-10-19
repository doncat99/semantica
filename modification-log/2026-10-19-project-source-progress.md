# Project source progress

- Reason: the project artifact worker emitted only aggregate extraction and embedding counters, leaving Library materials without their own measurable progress.
- Reused owner: `_extract_project_sources` and its native parallel queue; no separate scheduler or fact model.
- Method: include per-source completed, restored, total, in-flight, and queue state in each phase event while preserving the aggregate counters and source identity.
- Affected callers/data: worker progress metadata consumed by OntoScience; no snapshot or persisted fact schema change. Old workers still omit the optional field.
- Verification: `tests/test_semantic_artifact_scheduling.py` (interleaved two-source extraction and aggregate conservation); packaged native release and real App acceptance must follow the immutable pin update.
- Upstream merge: the event field is additive; keep this progress ownership in the artifact builder when rebasing on upstream.
