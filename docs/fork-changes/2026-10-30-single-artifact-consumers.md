# Single artifact publication and read-only native Explorer

- Record ID: 2026-10-30-single-artifact-consumers
- Date / author: 2026-10-30 / repository contributors
- Status: implemented-verified
- Fork base revision: 03067db84 (local main)
- Upstream reference: not refreshed; this is a correction to fork-owned behavior
- Related records: 2026-10-29-native-consolidation.md; host consolidation records

## Reason and scope

OntoScience must consume one published artifact, without full graph copies in
query/report/Explorer work directories or a mutable Explorer shadow graph.
The previous fork introduced `.explorer.json` loading and persistence in
ed2af3a561122827a9315343dcd8496175628df2. Direct builder calls also retain an
optional `snapshot.json` output distinct from the worker publication path.
This record was started retrospectively after the initial Explorer edits; the
required before-implementation record was missed. No earlier evidence is invented.

## Native capability assessment

- Native owners: `ContextGraph.load_from_file/save_to_file`,
  `GraphSession.from_file/record_decision`, native Explorer routes,
  `semantic_artifact_builder.build_semantic_artifacts`, `semantic_worker._dispatch`.
- Inspected consumers: host runtime, query, Explorer launcher; fork native pipeline,
  checkpoint, query-worker and semantic-artifact tests.
- Repair the owners; do not add a converter, knowledge store or fallback.
  Current ContextGraph already reads canonical_name and relations; a prior claim
  that this format necessarily loses names/edges is superseded by the actual
  loader and `test_semantic_artifact_loading.py`.

## Approach and actual changes

- Always load the supplied graph; remove shadow-file precedence and writes.
- Editable standalone sessions persist decisions to their sole native source;
  published OntoScience sessions are explicitly read-only.
- Reject mutation HTTP operations while retaining native read/query/export APIs.
- Remove the optional `persist_snapshot` output and make the builder the sole
  serializer; the worker forwards the exact builder file and digest. No
  `snapshot.json` is created alongside `semantic-graph.json`.
- Host uses contained canonical paths with a separate ephemeral runtime cwd.
- No formal profile deletion or paid extraction; no old-data relabeling.

## Verification and limitations

- Initial Explorer red specification: two failures, one pass before owner repair.
- Initial host scoped regression: four files, 59 passed.
- Explorer initial regression: 141 passed; one failed because the checkout has no
  `semantica_mcp` module imported by an existing API-alias test. Not counted passed.
- Canonical artifact schema, receipt/adoption lifecycle and publication protocol
  still require architectural review; removing copies is not removing that layer.
- No published artifact/pin, packaged ESG, warm rebuild or production migration
  acceptance from this change yet.

## Upstream merge assessment

- Disposition: pending upstream review. Drop the fork shadow-file behavior.
- Incoming upstream revision: not reviewed in this change.
- Keep native loader, graph mutation owner and route capabilities; rerun Explorer,
  semantic worker/query, checkpoints and host process tests after a merge.

## Dated follow-ups

### 2026-10-30 implementation and verification

- The optional `persist_snapshot` argument and second `snapshot.json` write were
  removed from `build_semantic_artifacts`. The single builder output is
  `semantic-graph.json`; `_dispatch` forwards its path and digest without
  serializing the in-memory artifact again.
- Host query, incremental build, reading-report/evidence and Explorer consumers
  now resolve the canonical object-store path. Their per-run full graph copies
  were removed. Explorer receives an isolated working directory and starts in
  read-only mode; its shadow `.explorer.json` load/write path was removed in the
  native `GraphSession` owner.
- Focused host regression: 6 files, 97 tests passed; the affected daemon
  regression rerun passed 60 tests and daemon typecheck passed. The affected
  fork regression passed 113 tests with 7 dependency deprecation warnings.
- Canonical-path admission now verifies the supplied SHA-256 before any native
  query/report/Explorer process receives a path. Build staging no longer uses
  the old run-local checkpoint-presence condition to retain a directory; the
  controlled checkpoint dataset remains the only recovery owner.
- This removes duplicate materializations, not the canonical graph artifact or
  the fork's `SemanticArtifact`/`snapshot_id` data contract. Those remain a
  separate architectural issue and are not represented as resolved by this
  change. Immutable release publication and packaged ESG acceptance remain
  pending.

### 2026-10-30 release contract correction

- The host launches the published Explorer with `--read-only`; the fork CLI now
  owns that flag and enforces it in the native `GraphSession` and HTTP app.
- The host cannot use the old pinned artifact for this contract. The fork commit
  and immutable release pin must be updated together before packaging.
- The builder and worker retain one native semantic-graph serialization. The
  `SemanticArtifact` aggregate and its snapshot identity remain an unresolved
  architectural boundary; this record does not claim that boundary is removed.
