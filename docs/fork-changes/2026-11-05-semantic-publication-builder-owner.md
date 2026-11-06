# Name the native publication builder by its current owner

## Native assessment and scope

Inspected fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`, including
uncommitted G4 changes. The existing native production builder produces native
publications and reference-based projections. Its module name still referred to
the superseded artifact builder, obscuring current ownership.

Moved the existing owner in place from `semantica/semantic_artifact_builder.py`
to `semantica/semantic_publication_builder.py`. Updated worker imports and all
current Python test/source-inspection references. No compatibility module,
alternate implementation, runtime dispatch or new protocol was introduced.
The worker build operation and its existing callable names remain unchanged;
this change names the module owner without changing computation semantics.
Historical change records retain their inspected paths as historical evidence.

The offline paid-results adoption owner and its tests are updated in the same
coordinated delivery by their assigned owner. Host fixture/worker-test imports
are reported to the integrator for cross-repository alignment and a fixed
artifact rebuild. Native parser/reader/source files remain byte-identical, so
this rename does not invalidate parsed material identity. Build processing
identity binds the renamed current owner; offline adoption must certify the
mechanical rename before reuse across that identity boundary.

## Regression evidence

A red specification requires the new owner module, physical absence of the old
module, and the worker's canonical new import. It failed before the move.
Focused verification covers cold worker import isolation, source windows,
worker/pipeline builds, processing identity, PDF ownership, bundle inventory,
and scheduling:

```text
.venv/bin/python -m pytest tests/test_semantic_worker_imports.py tests/test_native_source_windows.py tests/test_native_build_worker.py tests/test_native_build_pipeline.py tests/test_project_processing_digest.py tests/test_pdf_reader_ownership.py tests/test_bundle.py tests/test_semantic_artifact_scheduling.py -q --tb=short
93 passed in 9.30s
```

`git diff --check` also passed. The integrator records immutable artifact
and host-consumer evidence separately. No real model calls were made.

## Limits and upstream disposition

The rename does not close G4 or establish real ESG capacity. The current fixed
artifact must be rebuilt and host consumers checked before runtime acceptance.
Upstream disposition remains pending; preserve the single module owner during
future merges. No persisted-data migration is part of the module rename.
