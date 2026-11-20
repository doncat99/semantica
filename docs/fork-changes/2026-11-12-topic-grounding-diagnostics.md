# Located diagnostics for topic publication failures

- Record ID: 2026-11-12-topic-grounding-diagnostics
- Date / author: 2026-11-12 / Codex
- Status: verified-in-stated-scope
- Fork base revision: be868dec59fa1f079f3c265ad578a4a321c092a0
- Upstream reference: not inspected; local fork owner only
- Related issue / PR / commits / records: publication pending; OntoScience investigation `docs/engineering/library-topic-grounding-investigation-20261112.md`

## Reason and scope

A real Library build failed with `NATIVE_TOPIC_GROUNDING_MISSING`, but the error
did not identify the topic, citation, source, or character position. Preserve the
failure gate while adding content-free, structured diagnostic addresses.

## Native capability assessment

- Existing owner: `semantic_publication_builder.py::_publish_native_topics`;
  it delegates native observation lookup to `PublicationRecords.grounded_reference_page`.
- Callers: `build_semantic_artifacts::artifact_writing`; tests in
  `tests/test_native_producer_publication.py`; error consumer is OntoScience's
  Semantica worker diagnostic sanitizer.
- Decision: repair the existing diagnostic owner. No second lookup, extraction,
  publication implementation, dependency, or model call is added.
- Recent removals were not exhaustively audited; the inspected current call
  path directly uses the native publication owner.

## Approach and actual changes

- Add nested `topicGrounding` with topic/evidence IDs, source ID, start/end,
  a bounded failure reason, and range count when reference lookup misses.
- Assert these fields in the existing four fail-closed citation regressions.
- No quote, title, prompt, or source body enters diagnostics.
- No success criteria, stored schema, generation identity, activation gate or
  retry policy changes. No migration/deletion target is introduced.
- Model/network/dependency/cost impact: none.
- Not implemented: source-only supporting-reference mapping repair. Read-only
  investigation found a valid native relation `supportingRef` with a derived
  citation, but no independent native observation range on that support. The
  current scalar observation join does not traverse this support edge. Do not
  fix this by silently dropping citations or bypassing publication validation.

## Verification and limitations

- `.venv/bin/python -m pytest -q tests/test_native_producer_publication.py`:
  6 passed, including real isolated child-build publication/reuse coverage.
- Four diagnostic assertions failed before the diagnostic change and passed
  after it. All fixtures are temporary; no model/network requests are used.
- OntoScience worker sanitizer suite: 57 tests passed before the separate
  failure-trace retention change.
- Full fork suite, packaged artifact qualification and deployment not run.
- The `native-reference` reason identifies the failed join stage, not its
  internal source/owner/range subcause; the real case was distinguished through
  separate bounded, read-only storage queries.

## Upstream merge assessment

- Disposition: pending; retain while this native publication contract exists.
- Incoming upstream revision reviewed: not reviewed.
- Likely overlap: topic publisher/error diagnostics; preserve privacy fields
  and rerun native producer plus consumer sanitizer regressions after merge.
- Adapt/remove if the native owner provides equivalent located diagnostics.

## Dated follow-ups

- 2026-11-12: source-only diagnostic change tested; no deployed runtime changed.

### 2026-11-12 supplementary mapping and recovery correction

The earlier diagnostic-only scope above is superseded by the following owner
repair. `PublicationRecords.grounded_reference_page` accepts a typed reader and
structural reference proof. Indexed source membership, material/representation,
source address/native scalar range, admitted relation operation and main evidence
ownership must all match. The join follows the exact accepted `supportingRef`;
it reuses existing evidence and never invents an observation or calls a model.
Unknown addresses, changed representations, foreign sources, invalid ranges and
unowned relations cannot publish. No schema migration or alternative read path.
Reads are reference-only, bounded to 128 ranges and 12288-character indexed
windows, with cancellation and existing output budgets.

Located errors distinguish supplementary source, ownership, unknown address,
range mismatch and missing accepted relation, without quote bodies. Warning
events drain once per receipt; their pending queue is bounded with backpressure,
and absent listeners do not retain or wait for warning events.

Project progress reserves 42–62 for source classification, 62–90 for entity
resolution, 90–93 for facts, 93–96 for organization and 96–99 for publication.
Long stages emit elapsed/substep/count heartbeats without time-driven percentage
increments. Topics report completed/total counts before indexes and activation.

Verification: six isolated supplementary cases cover legal support without
independent entities, foreign source, changed representation, unknown address,
out-of-range and unowned relation. The legal case executes the real topic
publisher. A separate subprocess test crashes at artifact publication, resumes
to ready in a new process and reopens in a third process; paid-operation journal
entries do not increase. Existing identity/tamper/missing-checkpoint tests retain
the recovery fences. Full focused suite results and artifact qualification are
recorded in the consuming repository's dated investigation. Real-user recovery
requires the current source/report/checkpoint identities and a qualified bundle;
the presence of pending data alone never authorizes activation.

### 2026-11-12 host adoption correction

At inspected revision `8207f051889e8763d3c137f9b4fa2375faa53370`, native
canonical selectors produced `identity_profile` but selected scene hydration
rejected it. The existing `_selected_scene_fields` owner now requires exactly
one native profile IRI and retains scalar conflict validation.

Isolated real-checkpoint adoption then exposed `_scene_references`: 16 records
took 7.113 seconds, 7.057 in its broad provenance join. The same owner now
uses record-indexed ownedRecord, current publication membership and source
lookups, then reads mention/evidence addresses only for admitted records.
Cancellation, selected source filtering and unique address byte bounds remain.
No model call, cache, alternative evidence owner or schema change is introduced.
Callers are canonical scene hydration and scoped canonical selector filtering.
The indexed-access regression was red before the change; all 76 publication
record tests pass after it, including source scope and hydration budget tests.
Immutable artifact acceptance and isolated recovery must be rerun for this
source snapshot. Publication and deployment remain separate, unverified steps.
