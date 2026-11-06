# Stream native report family admission in ranking order

- Record ID: 2026-11-06-ordered-native-family-admission
- Date / author: 2026-11-06 / Codex
- Status: planned
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty worktree)
- Upstream reference: not inspected

## Reason and scope

Project organization materializes and sorts every qualified family, even though
report admission only needs ranked traversal. Source projection also duplicates
all evidence references into a project list. Remove these redundant retained
collections without changing family admission or exact community semantics.

## Native capability assessment

- Owners: `QualifiedFactIndex.family_page`, native qualified subject/predicate
  triples; `semantic_publication_builder` organization/report consumers.
- Existing bounded canonical selectors and native family pagination are reused.
- Extend the existing index with bounded ordered subject selection; no second
  storage owner, semantic algorithm, model call or persistent contract.

## Approach and actual changes

Planned: indexed subject-order batches, incremental admission, cited/scoped
reference lookup rather than duplicate global reference collections.

## Verification and limitations

Pending focused red/green regressions. Full topology and exact community remain
project-wide; oversized complete identity/conflict groups remain fail-closed.
No real model, running data, artifact or release operations are authorized by
this implementation seam.

## Upstream merge assessment

Pending; retain only while upstream owner needs this repair. Recheck ordered
pagination, admission oracle and native extraction handoff on merge.

## 2026-11-06 implementation and focused verification

Status: verified in stated scope.

Changed the existing `family_page` owner to accept a distinct ordered subject
scope of at most 128 IDs. SPARQL joins and orders that scope before cursor/limit;
source-support, required-family and byte-budget checks remain unchanged. Builder
sorts only existing topology vertex IDs, streams families in bounded subject
windows, and preserves the original source-count admission order. Removed the
duplicate project evidence list. Report lookup retains only admitted entity/fact
supports; topic grounding and publication retain only actually cited references.
All original reference objects remain attached to the source owner.

Red evidence: new ordered family pagination failed with unexpected `subject_ids`;
new builder boundary assertion failed with missing `subject_ids`. Both passed
after implementation. The original body-budget test required the now-removed
full-project report collection; it now verifies lossless source references plus
exact admitted report references and accepts the streaming iterator.

Commands (all `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -I -B -m pytest -q`):

- `tests/triplet_store/test_qualified_fact_index.py tests/triplet_store/test_fact_projection.py tests/test_reading_report_admission.py tests/test_native_global_body_budget.py tests/triplet_store/test_publication_records.py`: 64 passed, one outdated boundary assertion failed; 106.97 seconds.
- Corrected `tests/test_native_global_body_budget.py::test_model_report_input_does_not_retain_all_project_quote_bodies`: one passed, 7.64 seconds.
- `tests/test_native_build_pipeline.py tests/triplet_store/test_fact_projection.py`: eight passed, 11.94 seconds.

No real models/network, artifact builds, real ESG capacity run or full repository
suite. No running state or data touched. Stored triples and extraction semantics
are unchanged. The existing broad `PROJECT_PROCESSING_DIGEST` includes edited
source files, so its value changes automatically; reuse under another digest
still requires the host's exact compatibility certification rather than an
assumed unchanged recipe.

Remaining constraints: topology and exact community stay project-sized; ranked
vertex IDs and admitted complete required families remain resident. Complete
identity components and conflict partitions retain their existing explicit
budgets and can fail on a single oversized group. Source reference arrays remain
resident (the duplicate global collections were removed). Every family page also
retains the existing native reconciliation-complete check. This change does not
establish ESG end-to-end capacity or close G4 on its own.
