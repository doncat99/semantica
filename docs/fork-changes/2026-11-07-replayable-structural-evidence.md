# Replayable structural evidence coordinates

- Record ID: 2026-11-07-replayable-structural-evidence
- Date / author: 2026-11-07 / Codex
- Status: implemented-unverified
- Fork base revision: 586fbb919823b01f2c9c805c70ac26cd552df685
- Upstream reference: not inspected
- Related issue / PR / commits / records: pending

## Reason and scope

The native publication builder rejected a real ESG rebuild with
`NATIVE_EVIDENCE_RANGE_MISSING`. Structural table evidence without scalar
coordinates was being admitted into the aggregate evidence set even though it
cannot be replayed by the bounded native reader. This change keeps the native
reader as the sole evidence owner and admits only structural records with exact
scalar coordinates.

## Native capability assessment

- Existing owner and inspected files/symbols: `semantica/semantic_publication_builder.py`, `_structural_evidence`, `_docling_cell_evidence`, and native location readers in `semantica/semantic_document_reader.py`.
- Actual callers / config / exports / tests / recent removals checked: structural evidence callers and native publication tests.
- Decision: repair native owner.
- Evidence no second implementation is introduced: no new reader, storage, or citation path was added.

## Approach and actual changes

- Changed files and why: `semantica/semantic_publication_builder.py`; skip page-only/table-only structural locations that lack exact scalar ranges before replayable evidence conversion.
- Contract / consumer / stored-data impact and migration or deletion targets: no schema change; failed publication remains pending and produces no adopted data.
- Model / network / dependency / cost impact: none.
- Planned but not implemented: upstream comparison and full ESG rebuild verification.

## Verification and limitations

- Commands and results: `python -m pytest -q tests/test_native_producer_publication.py tests/test_semantic_artifact.py -q` attempted; blocked by missing local `pyoxigraph` dependency before affected assertions ran.
- Checks not run and why: real rebuild not yet rerun; requires the rebuilt native artifact.
- Known risks / unresolved questions: if a model cites a coarse structural location directly, the existing fail-closed path will still reject it; such a citation needs an exact native range from the producer.

## Upstream merge assessment

- Disposition: pending; upstream revision not inspected.
- Incoming upstream revision reviewed: not yet.
- Overlapping native owners / likely conflicts: `_structural_evidence` and native location projection.
- Conditions to retain, adapt or remove this change: retain only while upstream does not provide equivalent exact-coordinate admission.

## Dated follow-ups

2026-11-07: implementation completed; focused tests blocked by missing `pyoxigraph` in the local environment.
