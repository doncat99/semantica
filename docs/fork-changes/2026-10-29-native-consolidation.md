# Native consolidation: one comparison owner, no snapshot knowledge engine

- Date: 2026-10-29
- Status: implemented; focused source checks passed; publication/product acceptance pending
- Fork base revision: 5776e73bc1eb71050e7e0538e190d550a1656c5a
- Upstream reference: local 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0; not claimed current
- Related record: 2026-10-27-native-artifact-worker-contract.md

## Reason and scope

Implement the approved native-consolidation plan. Investigation and data operations
are restricted to OntoScience and its fork chain. No other project's database is
an input or migration target. Preserve existing contextual-identity and reading-
report changes; do not attribute them to this consolidation.

## Native capability assessment

TemporalVersionManager.compare_versions and compare_collections both implement
indexed collection differences. They must share one core. Stable edge IDs must
survive parallel qualified facts; duplicate IDs must fail closed.

OntoScience launches semantic_worker, which builds with persist_snapshot=False
and writes one semantic-graph.json. The host stores references to that artifact,
not a second snapshot payload. Query, Research and reports consume that artifact.
No OntoScience caller uses GraphStore.append_snapshot/commit_snapshot/read_snapshot,
Neo4jStore snapshot persistence, TypeDBStore, or retrieve_snapshot_context.
extend_semantic_snapshot has only those unused database APIs and tests as callers;
the builder re-export is unused by production. Do not move this engine elsewhere.

Native identity and facts remain EntityResolver, EntityMerger and ConflictDetector;
keyword/semantic remain ContextRetriever and VectorRetriever. Product evidence DTOs,
receipt validation, immutable artifact identity and checkpoint recovery remain.

## Approach and actual changes

TemporalVersionManager now owns one indexed comparison core used by both public
comparison paths. Explicit edge IDs distinguish parallel qualified facts; duplicate
IDs fail closed. New native versions store nodes/edges once; existing versions keep
their bytes/checksums and remain readable through the existing collection adapter.

Deleted snapshot_operations.py, typedb_store.py, GraphStore snapshot entry points,
Neo4j snapshot JSON/per-record writers/readers, the unused database snapshot context
retriever and the builder's unused re-export. Native Neo4j CRUD is unchanged. This
is removal of an unused extension, not a new backend or a database migration.
No database connection, record count or cleanup from another product is evidence.

Search preparation serializes only fields consumed by native keyword/vector search.
It no longer copies document bodies or entity/evidence metadata into the search
projection. Candidate selection, scores, order, source scope and the 1000-result
wire limit are unchanged. The regression rejects accidental serialization of
unconsumed payloads, while preserving grounded results.

The actual file-artifact protocol remains. No format/version bump, new snapshot
engine, model path, compatibility fallback or new checkpoint framework was added.
Existing checkpoint upgrade/install/journal recovery already owns verified offline
migration and duplicate cleanup. Updated stale tests now assert byte-exact paid
result retention, explicit offline migration, restart and removal of duplicate
carriers instead of requiring a complete second checkpoint under evidence/.

## Verification and limitations

- Focused fork regression: 263 passed, three existing temporal warnings. Covers
  change management, qualified facts, keyword/vector order and scope, query worker,
  artifact integrity and native ownership. The new search projection test failed
  before the fix with PydanticSerializationError and passed after the fix.
- Scoped Git-tree wheel, installed independently: 258 passed, three temporal
  warnings. Includes offline migration, restart, cross-process build/query and
  native SQLite persistence. Deleted snapshot/TypeDB modules are absent from the
  installed wheel. The first target-directory attempt let a test's deliberately
  cleared PYTHONPATH load the dirty environment in its subprocess; the installed
  environment resolves both parent and children to the scoped wheel. Its first
  SQLite timing sample exceeded 100 ms; the unchanged gate passed in the installed
  run. No timing threshold was relaxed.
- Host focused checks: 64 passed across six files; separate worker retry 74 passed.
  The first combined worker attempt failed before collection in concurrent dist
  cleanup (ENOTEMPTY); the isolated retry passed. Host root typecheck passed.
- Host guard failed on three already missing Explore screenshot references in
  docs/engineering/explore-graph-routing-20261029.md, outside this source change.
- Mixed dirty-checkout checkpoint regression: 50 passed, two failed. The separate
  contextual-identity draft introduces extractionContract=grounded-identity-profile-v1;
  old migrated results cannot supply the new profiles. Its completed-only build
  guard fails closed; direct-helper legacy tests expose the contract difference.
  No paid request was made and no old output was relabeled as new-contract output.
  These concurrent edits are excluded from this consolidation's release source.
- Auto Test change-verification selected library-knowledge-mainline and
  knowledge-secondary-states (105 API contracts); preparation timed out before
  execution, with late-cleanup "Server is not running". This is blocked, not passed.
  Cases capability-library-prepare, journey-library and
  journey-knowledge-research-workflow keep their existing owners and hard gates;
  no baseline or expected outcome was relaxed.

Read-only real cached ESG artifact: 38 document representations, 297,786,469 bytes,
SHA256 63d12c5ff7d4fc04a5eeb4ef7b2d33f6dd83a5dd60aaaa11fba45989d616c181.
ESG occurs 304 times in source text; 649 overlapping evidence spans contain it;
native keyword returns 729 items (649 evidence, 79 assertions, one relation).
All result evidence IDs resolve. Counts measure different objects, not recall loss.
Network was forbidden and paid extraction/generation/embedding counters stayed zero.
This read-only measurement is not a warm rebuild or packaged acceptance.

The same local sample before/after search projection: preparation 70.919 -> 7.672
seconds; keyword 0.432 -> 0.416 seconds; peak RSS 1,589,198,848 -> 1,373,765,632
bytes. Serialization 5.745 -> 4.938 seconds. Artifact bytes/digest and all 729
matches are unchanged. This is a single sample under concurrent load, not a
percentile performance result. No database bytes were measured or mutated.

Runtime delta against this work's 5776e73 baseline: +49/-589, net -540 lines.
Against fixed upstream 0a2731c: added runtime files 22/6,698 lines -> 20/6,456
lines (242 fewer, 3.61%). Overall runtime diff against that upstream remains
+8,807/-1,171; against the previous host pin ed2af3a it is +1,002/-1,863,
net -861. The latter includes intervening committed changes, not just this task.
No code relocation is counted as savings. The fork still has substantial product
protocol code; these numbers do not establish that all extensions are thin.

Baseline comparison before the preceding six packages is
ed2af3a561122827a9315343dcd8496175628df2. Publication, host pin and packaged real ESG
build/restart/token acceptance remain pending until separately verified.

## Upstream merge assessment

- Disposition: adapt native comparison owner; drop unused fork database snapshot extension.
- Incoming upstream revision reviewed: not refreshed.
- Overlap: change_management/managers.py and graph_store native APIs.
- Required checks: comparison, artifact integrity, cached build, keyword/semantic,
  identity/qualified facts, checkpoint migration, host contracts, packaged acceptance.

## Dated follow-ups

2026-10-29: preimplementation record; no tests or release claims yet.

2026-10-29 follow-up: implemented the changes and recorded the source verification
above. Concurrent contextual-identity/reading-report work remains owned separately.
