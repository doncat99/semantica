# Remove aggregate knowledge snapshot APIs

- Record ID: 2026-11-05-knowledge-snapshot-api-removal
- Date / author: 2026-11-05 / OntoScience remediation
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty working checkout)
- Upstream reference: local upstream/main inspected during G4 audit; these APIs also exist upstream, which does not satisfy the current single knowledge owner contract
- Related records: OntoScience deep-relationship-remediation-plan-2026-11, G4

## Reason and scope

The native knowledge build no longer consumes aggregate knowledge snapshots, but
public library APIs could still recreate and persist a parallel graph copy.
Retire that executable surface and its consumers, including copies inherited
from upstream. Independent ontology revision management and event temporal
semantics remain supported.

## Native capability assessment

- Inspected owners: AgentContext.checkpoint/diff_checkpoints/flush_checkpoint/
  _capture_checkpoint_state; ContextGraph.state_at; both TemporalVersionManager
  classes in change_management.managers and kg.temporal_query; VersionStorage
  knowledge tag/mutation methods; exports, tests and change_management_usage.
- The only production caller of the snapshot manager was AgentContext; current
  semantic_worker/builder/query has no caller. Host apps/packages/engineering/e2e
  were checked by the integration owner with no knowledge API consumer.
- OntologyVersionManager independently uses VersionStorage and checksum helpers.
  Its stored ontology revisions must remain valid and survive restart.
- Decision: delete retired owners in place. No replacement snapshot implementation,
  compatibility reader or migration-on-read is introduced.

## Approach and actual changes

- Delete both knowledge TemporalVersionManager implementations and exports;
  AgentContext checkpoint capture/diff/flush and retained checkpoint dictionary;
  ContextGraph.state_at; storage tags/mutation logs and their schema creation;
  knowledge snapshot normalization and obsolete helper exports.
- Restrict VersionStorage write/read/list to ontology revision shape. Old aggregate
  knowledge rows fail explicitly with ValidationError; offline delete remains
  available. The SQLite snapshot_data column is retained for independent ontology
  revisions and does not expose an accepted knowledge graph write contract.
- Delete only retired test classes/methods in mixed suites; preserve ontology,
  checksum, retraction, decision validity, temporal reasoning and provenance tests.
  Validity tests call the existing activity query owner instead of graph snapshots.
- Remove obsolete knowledge examples. Keep ontology examples and changelog docs.
- Preserve bounded native Explorer temporal scenes: selected <=128 nodes/links
  and <=256 KiB scope, no full graph persistence or deleted snapshot manager.
- Physically remove 12 precise orphan bytecode files for project_checkpoint,
  project_checkpoint_upgrade, snapshot_search and snapshot_operations from the
  canonical checkout (including their retired test pyc). Paths recorded in
  /tmp/g4-retired-pyc-deletions.txt. Do not modify an old immutable bundle.
- Stored-data reset boundary: existing knowledge snapshot databases/rows are
  unsupported; integration owner must stop active readers/jobs and perform
  authorized offline physical deletion, protecting originals, user edits and
  required audit evidence. Normal reads never recreate or convert an old graph.
- Model/network/dependency/cost impact: none. No paid calls.
- Artifact rebuilding and real ESG acceptance remain integration-owner work.

## Verification and limitations

- Red before source deletion: tests/test_knowledge_snapshot_retirement.py,
  6 failed in 1.88 s; /tmp/g4-knowledge-snapshot-red.log.
- Initial integrated scope after consumer alignment: 412 passed, 1 skipped,
  11 subtests passed in 2.87 s; /tmp/g4-snapshot-green.log. Existing provenance
  deprecation warnings are unrelated. Final run including stale-row and ontology
  restart tests is recorded below.
- Retirement specs use installed-module imports/introspection and actual SQLite
  behavior so the exact same tests can verify a fixed artifact.
- This is source and focused regression evidence, not real ESG capacity,
  packaged digest qualification, product acceptance or release approval.

## Upstream merge assessment

- Disposition: keep deletion. Incoming exact revision not yet reviewed.
- Likely conflicts: upstream AgentContext checkpoint and both temporal managers,
  ContextGraph.state_at, storage tags/mutation persistence and snapshot examples.
- Do not restore those APIs during merges. Preserve independent ontology and
  activity/provenance semantics. Re-run retirement specs, change_management,
  context decisions/retraction/markdown, temporal semantics/provenance, kernel
  owner regressions and bounded Explorer tests after a merge.

## Dated follow-ups

- 2026-11-05: Final source scope: 417 passed, 1 skipped, 11 subtests passed
  in 7.28 s, including the 8 installed-module retirement checks, full
  change_management suite, preserved temporal/provenance and bounded Explorer
  cases. /tmp/g4-snapshot-green.log. Await integration rebuild and fixed-artifact runtime oracle; no
  release claim is made by this record.

- 2026-11-05 final verification: 466 passed, 1 skipped, 11 subtests passed
  in 7.27 s; /tmp/g4-snapshot-final.log. The sole skip is the pre-existing
  Windows-junction platform test (test_context_graph_markdown.py:632), because
  this run is macOS. No retirement, ontology, temporal or Explorer contract is
  skipped. Included the preserved mixed unreleased-changelog suite.
- Scope-only source SHA-256 manifest: /tmp/g4-snapshot-source-freeze.json
  (seven changed library modules, not the digest of the entire dirty fork).

### 2026-11-05 TMS closure and relay contract correction

The earlier scope scan was incomplete: an unused-by-builder public API is still
an executable contract. Removed `TruthMaintenanceSession.to_checkpoint` and
`from_checkpoint`, the complete JSON codec `_truth_maintenance_checkpoint.py`,
`TruthMaintenanceSnapshot`, the session/filter `snapshot` APIs, exports and
checkpoint/restart tests. Removed only the periodic checkpoint continuation
section of the differential suite; preserved independent closure-oracle and
metamorphic tests. Retracted support catalog contents can no longer be exported
and restored as a second knowledge payload.

`ContextRetriever.retrieve` now captures only `TruthMaintenanceContextFilter.version`.
The filter checks declared candidate/attachment facts and support IDs through
`TruthMaintenanceSession.has_fact`/`has_support` native hash indexes, and verifies
the same committed version before and after validation and after retrieval.
No all-facts/all-supports DTO or replacement snapshot name is introduced. This
preserves the existing caller-serialized session contract; this is not a new
thread-safe session promise. Work/retained memory is proportional to supplied
candidate dependencies, independent of unrelated session size. Atomic `apply`
working-state cloning remains algorithm state, not export/restore persistence.

Regression: three demand-read/retirement specifications failed before source
changes (`/tmp/g4-tms-demand-red.log`). The demand-read test prevents enumeration
of the underlying active facts/supports, and a generator that mutates the
session during candidate iteration must fail closed. Existing grounding,
last-support withdrawal, citation replacement, attachment, non-mutation,
version-gate and independent-oracle regressions remain exercised.

Removed six exact retired TMS bytecode files; list:
`/tmp/g4-tms-retired-pyc-deletions.txt`. A broader scan also identified stale
mutable `build/lib` generated output; the integration owner must delete/rebuild
that tree before constructing the final immutable artifact. Existing immutable
artifacts are not modified.

The current model relay contract is renamed consistently from
`knowledge.snapshot.generate/embed` to `knowledge.publication.generate/embed`
in the schema, worker guard, tests, and both worker acceptance scripts. This is
an authorization capability name, not an aggregate graph. The old values are
explicitly rejected by schema tests; there is no compatibility union. Host and
fork must be rebuilt together; old immutable worker inputs fail explicitly.
No external models or network calls were used in this source verification.

### Final definition classification

The complete definition and reference scans are recorded in
`/tmp/g4-all-snapshot-checkpoint-definitions.txt`,
`/tmp/g4-all-snapshot-checkpoint-references.txt` and
`/tmp/g4-all-definitions-after.txt`.

- Removed knowledge owners: both TemporalVersionManagers, AgentContext
  checkpoint/diff/flush/capture, ContextGraph.state_at, TMS portable checkpoint
  and full-session read snapshot. Parallel owners remove GraphBuilder/CLI
  temporal materialization, TemporalGraphQuery.reconstruct_at_time,
  TemporalTruthMaintenanceAdapter.query_at/TemporalFactSnapshot, and full-graph
  visual comparison consumers; their separate records carry verification.
- Retain independent ontology `OntologyVersionManager.create_snapshot`,
  `BaseVersionManager` abstract creation/checksum protocol, ontology-restricted
  VersionStorage save/get/list and checksum. No accepted knowledge payload.
- Retain `_RuleSnapshot`, `build_rule_snapshots`, `_match_snapshot`: immutable
  parsed fixed-rule descriptors used by the only incremental reasoning engine;
  they do not contain a knowledge graph or restore session contents.
- Retain AgentMemory `_snapshot_memory_state`: internal update/import rollback
  state only, no public persistence/restore knowledge API. `list_snapshot` is
  one locked page plus count for Explorer memories, not a second graph.
- Retain native `publication_records.checkpointed` and identity-index nested
  `checkpoint`: bounded Oxigraph durability flush batches; no serialized DTO or
  alternate graph. Their names are not snapshot persistence semantics.
- Retain Explorer `TemporalSnapshotFastResponse`/temporal `/snapshot` projection
  and `DistanceSnapshot`: request-scoped activity IDs and timestamp/hop-count
  outputs, no stored graph or restoration path. Existing route read bounds are
  a separate demand-access concern, not a reason to create graph copies.
- Other snapshot words are local values: TTL cache mutation isolation, fixed
  input-byte capture in parsers/SSRF credentials, graph-delta queries against
  two native graph URIs, and vector index search lock copies. None defines an
  aggregate knowledge snapshot persistence or restore owner. They must still
  meet their own owner resource contracts; absence of a removed API call is
  never treated as an exemption for a second persisted knowledge representation.

Upstream merges must not restore TMS JSON codecs, old relay names or snapshot
consumers. Re-run retirement/demand-read specs plus reasoning/context/relay
contract regressions and exact immutable artifact acceptance after merges.

- 2026-11-05 TMS/fork relay final verification: **493 passed in 4.72 s**,
  `/tmp/g4-tms-complete.log`. Command: `.venv/bin/python -m pytest -q
  tests/reasoning tests/context/test_truth_maintenance_demand_reads.py
  tests/context/test_truth_maintenance_filter.py
  tests/context/test_grounded_context_retrieval.py
  tests/test_knowledge_snapshot_retirement.py
  tests/test_semantic_artifact_contract.py
  tests/test_native_explanation_worker.py tests/test_semantic_artifact.py`.
  Scoped `git diff --check`, AST parsing and absence of four deleted files pass.
  Scope SHA-256/deletion manifest: `/tmp/g4-tms-source-freeze.json` (includes
  current shared ContextRetriever/reasoning exports, not whole-fork digest).
  No claim of packaged/ESG acceptance from this source-only evidence.
