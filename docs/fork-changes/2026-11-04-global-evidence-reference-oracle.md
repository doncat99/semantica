# Global evidence reference equivalence oracle

- Record ID: 2026-11-04-global-evidence-reference-oracle
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream reference: not inspected
- Related records: G4 native body budget remediation

## Reason and scope

The existing global body probe accepted releasing just one of thousands of
evidence objects. It also did not verify that reference projection preserves
complete IDs, quotes, locators and metadata. Strengthen the existing producer
regression before the builder replaces retained spans with source references.

## Native capability assessment

- Owner: `semantic_artifact_builder.py::_build_semantic_artifacts`,
  `_semantic_organization` and `_explanation_reports`.
- Inspected callers: source projection, native publication and report selection.
- Existing codec: `triplet_store/extraction_records.py::ExtractionRecords`
  already stores evidence ranges without copied source bodies, with bounded
  per-operation receipt validation. No unused paging API or second owner added.
- Existing test: `tests/test_native_global_body_budget.py` exercises actual
  parsed-source production without remote transport/model calls.
- Decision: reuse and strengthen the existing test owner only.

## Approach and actual changes

- Require zero captured original span objects at both global stage boundaries.
- Retain only a SHA256 fingerprint of each complete JSON span as the oracle,
  so oracle quote strings do not invalidate lifetime measurement.
- Compare every projected ID and full hydrated span twice, including locator
  and metadata fields. Check model references before report selection too.
- No runtime, dependency, network, cost or stored-data changes in this record.
- The builder implementation and bounded native reads are separate changes.

## Verification and limitations

- Red specification: `.venv/bin/python -m pytest -q
  tests/test_native_global_body_budget.py` failed both tests in 2.80 seconds.
  Deterministic retained 4104 originals / 120904 quote bytes; model retained
  1032 originals / 45128 quote bytes. ID/full-span equivalence passed before
  lifetime rejection.
- Green after builder integration: `.venv/bin/python -m pytest -q
  tests/test_native_global_body_budget.py tests/test_native_build_body_budget.py`
  passed all 5 tests in 15.01 seconds. Stored reference payloads recursively
  reject quote keys after hydration, including locators.
- The model probe's previous final `>20000` report-context byte assertion was
  unreachable before the lifetime fix and contradicted existing selection:
  an empty extraction chooses the first passage of each source. It now verifies
  the exact eight `Source N.` passages while separately requiring the full
  reference oracle to cover more than 20000 quote bytes. No selection behavior
  was changed to satisfy this assertion.
- These synthetic offline probes do not prove full G4 completion or
  packaged/ESG acceptance.
- Complete candidate/topology memory bounds remain a separate unresolved gap.

### 2026-11-04 reference hydration follow-up

- Added `tests/test_native_evidence_reference.py` to exercise the transient
  reference itself using the real native artifact/index writer and source
  reader request. No production implementation changed in this follow-up.
- A range crossing PDF-native page separators and three or more 12288-character
  windows preserves non-BMP Unicode, combining marks, complete locator and
  metadata on repeated full-span serialization. Captured reader calls must
  tile the accepted range exactly, and the reference must not cache the quote.
- Changing either the artifact or its reader index after successful hydration
  rejects the next read as an installation change. A same-length quote with a
  different accepted digest raises `NATIVE_EVIDENCE_RANGE_MISMATCH`.
- Verification: `.venv/bin/python -m pytest -q
  tests/test_native_evidence_reference.py tests/test_native_global_body_budget.py
  tests/test_native_build_body_budget.py` passed all 9 tests in 15.94 seconds.
- This is focused reader/reference evidence; the global candidate/topology
  bounds and packaged real-ESG acceptance remain outside this result.

## Upstream merge assessment

- Disposition: pending; incoming upstream not reviewed.
- Keep only while global reference projection is the current native producer.
- Rerun these probes and native source-window/scalar-grounding tests after merge.
