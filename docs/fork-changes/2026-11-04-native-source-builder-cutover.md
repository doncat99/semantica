# Builder source admission and bounded traversal cutover

- Record ID: 2026-11-04-native-source-builder-cutover
- Date / author: 2026-11-04 / Codex
- Status: verified-in-stated-scope; G4 remains incomplete
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe plus existing dirty native changes
- Upstream reference: not inspected
- Related records: native-source-window-reader, source-window-residency,
  native-source-location-addresses, native-source-consumer-fixtures (all 2026-11-04)

## Reason and scope

Earlier scheduling improvements still admitted the complete parsed JSON and body.
That was not an actual native range-reader cutover. Replace source admission and
its build consumers with the installed native document reader while preserving
immutable identity, exact window boundaries, occurrence identity and evidence.

## Native capability assessment

- Existing owners inspected: semantic_source_artifact.py::_load_parsed_source,
  semantic_document_reader.py source header/window/location/range APIs,
  semantic_artifact_builder.py::_extract_project_sources and _build_source,
  source.py::source_content_revision.
- Callers/tests: model and deterministic native build pipeline/publication,
  scheduling/recovery, exact source-window and scalar-grounding tests.
- Decision: repair and reuse the existing reader and builder. Delete production
  tuple admission, obsolete builder window splitter and substring-location
  helpers; no alternate parser, checkpoint, source body store or fallback.

## Approach and actual changes

- NativeParsedSource retains metadata and reader-backed text, windows, locations
  and scalar-address selectors. Admission validates original immutable bytes,
  artifact digest, current processing profile and representation identity without
  deserializing the complete parsed artifact. Window and scalar maps are lazy.
- Builder windows hydrate only active native ranges. Location/context selection
  delegates to the indexed reader. Extraction requires absolute producer offsets.
- Occurrence ordinals and line-relative passages stream source ranges no larger
  than 12,288 characters. Exact Unicode case matching, arbitrary whitespace,
  unextracted duplicate occurrences and long-line/tail semantics are preserved.
- Actual RSS reproduction found retained allocator growth from repeated 1 MiB
  hash-read allocation. Both existing digest owners now reuse one readinto buffer;
  digest algorithms and cancellation checks remain unchanged.
- No network/model/dependency change, paid result regeneration, new supported
  contract, stored-data migration, artifact pin, release or ESG acceptance.

## Verification and limitations

- Actual 16 MiB source admission runs in a separate process, checks exact tail
  hydration and requires admission RSS growth below 8 MiB. A red test also
  forbids whole-artifact read_bytes and map enumeration during admission.
- Admission/hash/exact traversal selection: 19 passed. Earlier native source
  window/build pipeline/publication/traversal selection: 29 passed; native
  lifecycle/checkpoint deletion/paid-result handoff selection: 19 passed.
- After lazy maps and SQL scoped native-range/cell queries, source windows,
  locations, admission RSS, traversal, actual native build/publish and native
  extraction selection: 66 passed in 11.74s. Focused diff whitespace check passed.
- These are focused overlapping checks, not a total repository test count.
- Remaining G4 gaps: builder-wide extracted/embedded result slots and job
  descriptors; complete structural context hydration before model batching;
  source/project evidence, entity, report/topology materialization and downstream
  global result budgets. No G4 pass or bounded end-to-end build claim.
- Upstream and real ESG/package acceptance not run in this work.

## Upstream merge assessment

- Pending; incoming upstream revision not reviewed. Likely overlap: native
  source reader admission, window identity and immutable source digest owners.
- Retain only where equivalent upstream native behavior is absent; adapt to a
  single owner. Rerun exact windows, grounding, occurrence/passage, cancellation,
  source RSS, model/deterministic native build and publication regressions.
