# Completed results and source identity

- Record ID: 2026-11-10-completed-results-and-source-identity
- Date / author: 2026-11-10 / OntoScience maintainers
- Status: implemented-unverified (focused specifications pass; product acceptance pending)
- Fork base revision: bb418942ed6ca8f6c54ec9773ba312070386564c
- Upstream reference: not refreshed during this change
- Related records: OntoScience `code-identity-coupling-audit-2026-11-07.md`; commits pending

## Reason and scope

Transport-bound source hashes changed on relocation or rename. Projection misses
then reconstructed observations whose accepted native projections already existed.
Generation replacement and ordinary result reads must not repeat completed work.
The historical production error is `Native fact projection differs from existing
derivation`; a read-only sample compared 418 projections without differences, so
its particular field-level cause is not established by this change.

## Native capability assessment

- Existing owners: `ExtractionRecords.source_projection`, immutable extraction
  operation bindings, `PublicationRecords`, `QualifiedFactIndex`,
  `IdentityCandidateIndex`, `SQLiteVecStore`.
- Callers inspected: `semantic_publication_builder`, `semantic_source_artifact`,
  `native_maintenance`; native lifecycle, handoff, projection and publication tests.
- Decision: repair existing owners. ConflictDetector remains the semantic reducer;
  no alternate resolver, cache database, snapshot engine or fallback reader added.

## Approach and actual changes

- Source identity explicitly selects project/source/material/accepted parse and
  semantic extraction inputs. Absolute path, display name and executable digest
  are excluded. The completed header retains the immutable accepted operation
  collection; normal lookup does not derive that collection by scanning facts.
- Completed publication lookup precedes source restoration; a failed newer task
  does not hide an active completed publication. Replacement preserves valid
  identity/fact decisions. Embedding changes reuse knowledge stages.
- Existing observation addresses are consumed directly. Removed occurrence
  ordinal reconstruction and repeated fact/identity projection production.
- Canonical consumers read committed decisions without reducer callbacks.
  Native endpoint/coverage/qualifier checks still reject malformed stored data.
- Offline `rebind_source_projection` verifies bindings and addresses before
  changing lookup subjects. Published IDs and accepted observations are unchanged;
  normal reads do not probe historical keys. Host migration handles parsed-source
  selectors separately, without rewriting their immutable carriers.
- Model/network impact: no new model or service; successful reuse makes no paid
  calls. Existing receipts and vector identities remain owned by their stores.

## Verification and limitations

- Focused native regressions: 124 and 185 tests passed in earlier affected runs;
  100 publication/fact/maintenance tests passed; malformed count/activation scale
  4 passed; corrupt-policy rejection passed.
- `tests/test_native_projection_lifecycle.py`: relocation/rename prohibit body
  reads and source rebuilding; embedding-only regression passes and permits only
  embedding calls, forbidding classification preparation, identity and fact
  reduction.
- Persistent 56,700-observation / 21,620-group activation: 2.614 seconds.
- Latest timed scale run: native read 14.641 s; semantic reduction 5.144 s;
  completion commit 0.224 s; total read/sort/reduce/commit 43.705 s; completed
  lookup 0.000664 s. Maximum RSS 768,999,424 bytes. Package acceptance ran
  concurrently. An earlier 26.15 s result is not a stable p95 or a first-build
  performance pass. Evidence: host `.tmp/identity-fact-scale-timing.log`.
- Full packaged ESG ready/report/evidence acceptance, idle cold/hot repetitions,
  original mismatch reproduction and full dependency-invalidation acceptance are
  not yet complete. Focused tests are not release acceptance.

## Upstream merge assessment

- Disposition: keep repair of existing fork owners; review on each upstream merge.
- Incoming upstream revision: not reviewed in this change.
- Likely overlaps: publication builder, extraction records, vector store.
- Adapt/remove only when the current upstream owner supplies these same identity,
  reuse, evidence and integrity guarantees; do not preserve a parallel engine.
- Required checks: native projection lifecycle, handoff, maintenance, publication
  integrity, scale and host Library acceptance against the exact packaged source.

## Dated follow-ups

- 2026-11-10: New native bundle acceptance passed. Host App packaging and isolated
  change-verification are running; delivery is not yet certified.
- Final focused owner run: 133 passed in 101.21 seconds (projection lifecycle,
  maintenance, source traversal, publication, qualified facts and vector handoff).
  Source-removal specifications verify affected membership replacement and
  immutable preservation of prior decisions; unchanged partitions skip reduction.
