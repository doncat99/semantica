# Installed acceptance consumes native publication owners

- Record ID: 2026-11-04-native-installed-acceptance
- Date / author: 2026-11-04 / Codex
- Status: implemented-unverified
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty working tree inspected)
- Upstream reference: not inspected in this acceptance consumer change
- Related issue / PR / commits / records: native G4 migration, pending

## Reason and scope

The installed acceptance scripts still imported the removed SemanticArtifact
aggregate and requested snapshot/retrieval/keyword artifacts that the current
worker no longer produces. Replace those consumers in place. This change does
not produce, qualify, publish, or pin immutable release artifacts.

## Native capability assessment

- Existing owner and inspected files/symbols: semantic_artifact_schema
  SemanticArtifactBuildRequest/ParsedSourceRef; semantic_worker._dispatch and
  _explain_evidence; semantic_query_schema native store, reader, query and record
  requests; semantic_query_worker.handle_request; semantic_source_artifact parser.
- Actual callers / config / exports / tests / recent removals checked: both
  .github/scripts/semantic_worker*acceptance.py scripts, native build pipeline,
  worker, query, record, producer-publication and explanation regression tests.
- Decision: reuse the current native producer, acquired query session, bounded
  canonical records, exact document reader, classification and explanation owner.
- Evidence no second implementation is introduced: no production owner is added;
  the deterministic loopback relay and organization-product simulator remain
  acceptance-only transport fixtures.

## Approach and actual changes

- Changed files: semantic_worker_acceptance.py verifies native pending receipt
  identity, no aggregate outputs and acquisition rejection; the model script
  exercises ready receipt acquisition/release/reopen, bounded point reads,
  classification, two-source keyword cursor pages, semantic original ranges
  and native evidence explanation using installed reader/index identities.
- Contract / consumer / stored-data impact: remove obsolete baseSnapshot,
  aggregate model imports and aggregate artifact consumers; supply exact parsed
  representation revisions and required native cache/store/report-owner paths.
  Deterministic builds remain pending without semantic index qualification.
- Model / network / dependency / cost impact: no dependency added. At runtime
  the existing controlled acceptance uses only its authenticated loopback relay
  and an in-memory host-product simulator, never a paid external model.
- Planned but not implemented: immutable bundle generation and qualification.

## Verification and limitations

- Commands and results: both scripts compile via ast.parse/compile; scoped
  git diff --check passes. Native query, record worker, explanation worker,
  build worker and build pipeline pytest selection: 37 passed in 3.08s.
  Acceptance reader helper was validated against DocumentReaderRequest using
  a real written reader/index artifact and current installation identities.
- Checks not run and why: installed bundle/OCR acceptance and loopback model
  acceptance were not executed; this task forbids model calls and release work.
- Known risks / unresolved questions: source/schema checks and owner regression
  are not end-to-end acceptance of these relocated installed scripts.

## Upstream merge assessment

- Disposition: pending; retain while the native worker contract remains current.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: build/query schema and installed
  acceptance scripts, document parser bundle inventory.
- Conditions to retain, adapt or remove this change: adapt to the canonical owner
  if its contract changes; never restore aggregate compatibility carriers.
- Required consumer/regression checks after merge: native worker, bounded query,
  records, explanation and relocated immutable-bundle acceptance.

## Dated follow-ups

- 2026-11-04: source-only validation; native artifact qualification remains open.
- 2026-11-04: the first complete dev artifact reached installed acceptance and
  failed at line 118: the script still required the removed `doctags` content
  copy. Replace that stale assertion with native document presence and rejection
  of duplicate DocTags/plain-text/flat-ODF carriers. Preserve the failure in host
  `.tmp/native-g4-topic-qualified-build.log`; no product gate or baseline changed.
  Extend the existing loopback scene assertions to native topics, selected members
  and a second acquired worker process. Requalification is pending; running the
  current acceptance consumer against the frozen artifact does not relabel its
  source digest or create a development receipt after a failed builder run.
- 2026-11-04: the next installed run passed parsing and exposed a real packaging
  defect: `ModuleNotFoundError: pyoxigraph` in the native OxigraphStore owner.
  The source test environment had the package, but semantic-worker-common did
  not request its existing tripletstore-oxigraph extra. Add that extra to the
  canonical worker dependency and regenerate all six existing platform/profile
  locks with their constrained uv commands; no other runtime package pins changed.
  Both acceptance invoke helpers now include bounded subprocess stdout/stderr on
  failure. The original failure remains in host
  `.tmp/native-g4-topic-installed-acceptance.log`.
  `tests/test_semantic_worker_release.py`: 15 passed, including dependency/lock
  checks and the loopback model/query/topic/reopen path. This is source evidence;
  exact installed artifact requalification remains pending. Consumers inspected:
  semantic_worker_release.build_bundle, bundle.build_bundle and all configured
  CPU/CUDA/DirectML profiles. Merge assessment: retain the dependency while the
  native publication owner requires Oxigraph; never substitute another store.
- 2026-11-04: the rebuilt installed artifact passed parser/OCR checks and reached
  the deterministic pending-publication assertion, where the consumer still
  indexed an absent `nativeIndexes.semantic` key. The current
  `semantic_artifact_builder._publish_native_indexes` emits only `keyword` when
  no embedding paths exist. Assert that exact key set instead of requiring a
  fabricated null descriptor. The model acceptance consumer still requires a
  real semantic descriptor for its ready publication. Failure evidence is host
  `.tmp/native-g4-topic-qualified-rebuild.log`; full requalification is pending.
