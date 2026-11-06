# Native extraction write/read payload budget alignment

- Record ID: 2026-11-07-native-extraction-byte-budget
- Date / author: 2026-11-07 / Codex native owner task
- Status: verified-in-stated-scope
- Fork base revision: 64509cd1b720ead8ee5ac4a3d57b000cb58f8c06
- Upstream reference: not inspected in this focused repair
- Related issue / PR / commits / records: parent G4/G56 acceptance remediation; PR pending

## Reason and scope

G56 failed at the frozen owner line 699 with `Native extraction fact read exceeds budget`.
This is a read budget failure, not evidence of factsDigest corruption. The existing
writer charged serialized triples under one GRAPH statement against 2 MiB; the
verifier charged full Quads, repeating the fixed graph URI per row. An insertion
could therefore succeed and its immediately verified receipt fail.

## Native capability assessment

- Owner: `semantica/triplet_store/extraction_records.py::ExtractionRecords.commit/_verify_receipt`.
- Consumers inspected: `semantic_extract/grounded_window.py::run_stage` and
  `semantic_publication_builder.py` extraction binding construction.
- Existing persistent native owner is repaired in place; no alternate reader,
  payload carrier, schema version, recovery path, or fallback was added.
- Tests: existing triplet_store field codec, persistent extraction handoff,
  projection handoff and window-reference handoff suites.

## Approach and actual changes

- Share canonical triple formatting between atomic insertion and verification.
  Verification charges triple bytes plus the three-byte row separator. The writer
  additionally includes operation metadata within the same 2 MiB envelope; this
  dominates the verifier's facts-only charge, including its last separator.
- Keep MAX_BYTES=2 MiB, MAX_QUADS=32768, MAX_OWNED=8192, scalar caps and both full
  Quad SHA256 integrity checks unchanged. A graph is fixed per operation with a
  fixed-length hashed project URI. Actual Quad text allocation therefore has a
  finite extra bound of MAX_QUADS times that fixed graph representation overhead;
  this budget measures typed RDF payload, not total Python RSS.
- Existing correctly persisted receipts/facts require no mutation: the current
  strict reader can verify them and resume through the normal accepted handoff.
  Genuinely missing/tampered data remains an error.
- `_project_processing_digest` hashes this owner, so the new immutable artifact
  changes the installed processing/recipe digest. Prompt/schema/model/vector
  semantics, acceptance digest codec, operation identity and stored fields are
  unchanged. Cross-recipe paid-result reuse requires the host's existing exact
  offline field/recipe certificate; this change does not bypass binding checks.
- No model/network calls or production database writes. No frozen artifact edits.
  A stopped copied accepted-handoff SQLite was read only to count its single
  entities envelope (90,718 bytes); it lacks full original grounding input, so
  exact real-payload replay was not claimed or required for this owner regression.

## Verification and limitations

- Red: new 280-entity regression admitted a triple payload below 2 MiB while its
  full Quad fact text exceeded 2 MiB; old commit failed at exact line 699.
- Green: same test verifies insertion, reopening, complete lossless reconstruction,
  and strict rejection after physically removing one fact.
- New 420-entity oversized payload test rejects before any graph insertion.
- `.venv/bin/python -I -B -m pytest -q tests/triplet_store/test_extraction_records.py tests/test_native_extraction_handoff.py tests/test_native_projection_handoff.py tests/test_native_window_reference_handoff.py`
  => 29 passed in 15.90 seconds, including cancellation/crash/restart paid-result
  reuse and native corruption rejection.
- Full product G56, real ESG capacity, artifact qualification and release checks
  remain parent-owned and were not run by this task. No duplicate-quad fix is
  included: that separate theoretical concern is not the observed G56 failure.

## Upstream merge assessment

- Disposition: pending; incoming upstream not reviewed.
- Overlap: native typed extraction field codec and atomic receipt verification.
- Retain only while upstream has differing insertion/read payload byte accounting;
  adapt/drop when the canonical owner offers equivalent bounded strict behavior.
- After merge rerun the four focused suites above and host fixed-artifact G56.
