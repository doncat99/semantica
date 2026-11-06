# Retire detached temporal closure and graph snapshot visualization

- Record ID: 2026-11-05-temporal-closure-and-visualizer-snapshot-removal
- Date / author: 2026-11-05 / Codex
- Status: verified-in-stated-scope
- Fork base revision: `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`
- Upstream reference: not inspected; local fork owner and callers inspected
- Related records: `2026-11-05-knowledge-snapshot-api-removal.md`

## Reason and scope

`TemporalTruthMaintenanceAdapter.query_at` selected historical supports and
created a second `TruthMaintenanceSession`, then returned all facts, supports,
and explanations as a detached `TemporalFactSnapshot`. The temporal visualizer
accepted complete graph snapshots only to calculate metrics. These are whole
knowledge copies outside the current live reasoning and metrics owners.

## Native capability assessment

- Existing owner: `TemporalTruthMaintenanceAdapter.sync`, `advance`, `facts`,
  and `explain` maintain the live temporal closure. `TemporalVisualizer`
  already has `visualize_metrics_evolution` for metric history.
- Callers checked: reasoning export, temporal reasoning/context graph/differential
  tests, visualization convenience dispatch, comprehensive test and usage docs.
- `AgentMemory._snapshot_memory_state` is in-memory rollback for user-memory
  replacement/import. `list_snapshot` returns the current bounded user-memory
  page plus count to Explorer. Neither is a knowledge graph snapshot; retained.
- Decision: remove the detached knowledge closure and full-graph visualizer
  consumer in their native owners. No replacement path or second store added.

## Approach and actual changes

- Removed `TemporalFactSnapshot`, `query_at`, export, visualization comparison
  method and dispatch. Deleted their public examples and retired assertions.
- Kept time validity, hindsight, source immutability and failure-atomicity tests
  through live `advance`/`facts`/`explain` behavior.
- No stored-data migration, model call, network access or dependency change.
- Planned but not implemented: no broader temporal API change.

## Verification and limitations

- Red specification before source edit: `pytest tests/test_temporal_snapshot_retirement.py -q`
  yielded 2 failures for the two still-present APIs, 5 passes.
- After the concurrent TemporalGraphQuery/CLI retirement completed,
  `pytest tests/reasoning/test_temporal_truth_maintenance.py
  tests/reasoning/test_temporal_truth_maintenance_context_graph.py
  tests/reasoning/test_temporal_truth_maintenance_differential.py
  tests/visualization/test_visualization_comprehensive.py
  tests/test_temporal_snapshot_retirement.py -q`: 88 passed in 2.16 seconds.
- `rg` over `semantica`, `tests`, `docs` found no retired symbol calls; only
  explicit absence assertions in the retirement spec. Generated `build/lib`
  remains a build artifact to regenerate from current source.
- Full fork suite, installed artifact and ESG acceptance are not claimed here.

## Upstream merge assessment

- Disposition: keep until upstream has an equivalent current-owner temporal
  reasoning and metric API that meets the single-implementation contract.
- Incoming upstream revision reviewed: none.
- Likely conflicts: reasoning exports, temporal adapter and visualizer facade.
- On merge, recheck all callers and run temporal reasoning and visualization
  tests; remove this fork change if upstream already retires these APIs.

## Dated follow-ups

- 2026-11-05: Initial removal and scoped verification recorded.
