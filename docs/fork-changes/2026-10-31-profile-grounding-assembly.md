# Preserve native profile grounding during window assembly

- Record ID: 2026-10-31-profile-grounding-assembly
- Date / author: 2026-10-31 / OntoScience contributors
- Status: verified-in-stated-scope
- Fork base revision: 21717d3af9583d594c2f958eff30ac618f2c7b66
- Upstream reference: not inspected for this targeted fork contract repair
- Related records: tests/test_project_identity.py

## Reason and scope

The packaged ESG Report run completed 2,994 extraction windows and embeddings,
then failed in `_assemble_grounded_windows`. The native extractor locates quotes
with whitespace differences; assembly incorrectly required literal equality to
the model quote. Existing paid checkpoint results must remain reusable.

## Native capability assessment

- Native owner: semantic_extract/methods.py::_exact_occurrence, used by
  extract_entities_llm for identity profile grounding.
- Consumer: semantic_artifact_builder.py::_assemble_grounded_windows followed by
  _build_source, which requires exact source slices and contained owner/instance.
- Decision: reuse the native locator in assembly. No second matching algorithm,
  pipeline, cache, or knowledge representation is introduced.

## Approach and actual changes

- Assembly verifies stored integer offsets against the native locator, then
  retains exact source evidence. Owner/instance whitespace is grounded through
  that same locator so those fields remain exact substrings of source evidence.
- Tests cover normalized spaces, surrounding whitespace, multiline owner,
  projection offsets, and rejection of incorrect stored offsets/content.
- No model/network dependency or extraction policy change; no cache deletion or
  migration. Existing grounded checkpoint entries use the same contract.

## Verification and limitations

- Before repair, normalized/surrounding-whitespace cases failed assembly.
- `.venv/bin/python -m pytest -q tests/test_project_identity.py
  tests/test_semantic_artifact_native_extraction.py
  tests/semantic_extract/test_grounded_llm_extraction.py`: 84 passed.
- Packaged ESG success and full warm rebuild cost evidence remain pending;
  focused tests do not establish production acceptance.

## Upstream merge assessment

- Disposition: pending; no incoming upstream revision reviewed.
- Reassess extractor grounding and builder consumer together on merge. Retain a
  single native locator and run the above regressions plus packaged build and
  same-input warm rebuild checks before declaring delivery complete.
