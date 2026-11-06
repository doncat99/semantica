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

2026-11-06 correction (inspected revision b80cc4ff07d1017ef35843629b2c99b4b4b2c1f8):
The skip-only repair above was insufficient. ESG source 20 failed when a model
supporting ref cited a rich table cell without linear source coordinates. These
records have exact native scalar `quoteAddress` coordinates and are replayable;
discarding them would lose valid support. `_EvidenceReference` now delegates
their replay to the existing `_NativeSourceLocations.by_ref` owner, retaining
length and SHA256 verification and no retained quote. `_docling_cell_evidence`
keeps these records, and `_publish_native_topics` uses the same native scalar
address with the existing grounded-reference query. Partial coordinates and
missing addresses still fail closed. No parser, schema, model, vector space,
storage owner, or reader implementation was changed; paid-result adoption must
separately certify the exact installed artifact pair before resumption.

The rich-cell regression reproduced `NATIVE_EVIDENCE_RANGE_MISSING` before the
fix. `.venv/bin/python -m pytest -q tests/test_native_evidence_reference.py
tests/test_native_source_windows.py tests/test_native_producer_publication.py`
then passed 33 tests in 5.60 seconds. A read-only audit of all 38 ESG native
indexes replayed all 46 rich-cell records without linear coordinates across
five sources with exact length/digest checks and zero model calls. These are
focused source checks, not real publication or release acceptance. The rebuilt
artifact and resumed real build remain unverified. Upstream was not inspected;
retain this repair while the native replay contract requires it.
