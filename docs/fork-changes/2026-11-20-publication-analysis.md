# Bounded publication analytics

- Date: 2026-11-20
- Status: implementation in progress; artifact qualification pending
- Inspected revision: a6a716d2dbedf9c220b1048f901c4c00e2d06203

## Native capability assessment

Explorer `routes/analytics.py::get_analytics` delegates to
`CentralityCalculator`, `CommunityDetector`, `ConnectivityAnalyzer` and
`GraphValidator`; PageRank also exists in `CentralityCalculator`.
The query worker has no analytics operation. OntoScience's Analyze currently
counts pages, which is not equivalent to these algorithms.

## Implementation and consumers

`kg/publication_analysis.py::analyze_publication` supplies an explicitly bounded
complete publication graph to these owners, with no second metric algorithm.
The current query worker exposes `analyze`, binding project and generation.
OntoScience HTTP, CLI and workspace must consume this operation together.
The previous host page-count analysis is the deletion target.

Input bounds: 1024 nodes, 2048 relationships, 32 pages, 2 MiB projected input,
5 seconds; native pages remain at most 128 rows/256 KiB. Output is at most
1 MiB. Budget exhaustion returns incomplete with no metrics, never metrics
for a silently truncated graph. Partial metric failures remain explicit.
The daemon also terminates/reaps workers on cancellation or deadline.
These are query/projection budgets, not physical disk-read measurements.

## Regression evidence and limitations

`tests/kg/test_publication_analysis.py` first failed because the native
publication entry point was absent. It checks persisted publication results
against existing metric owners and rejects metrics on incomplete input.
Focused green results and artifact evidence will be recorded after execution.
Large-project computation and physical storage reads remain unqualified.
No persisted schema changes, model calls or new dependencies are introduced.

## Upstream merge assessment

Pending: compare upstream worker protocol and analytics owners before merging.
Keep one calculation implementation per metric; this module only supplies input.

## 2026-11-20 verification and temporal projection correction

The focused analysis/worker run passed 22 tests. The subsequent combined native
publication, canonical fact, analysis and worker run passed 125 tests. These
results exercise source code; they do not qualify a rebuilt artifact or App.

Inspection of `PublicationRecords._projected_scene_link` found that reading the
representative observation's effective time incorrectly attributed that time
to a canonical fact with multiple supports. `_fact_valid_time` now uses the
existing `kg.temporal_model.parse_temporal_value` and the exact immutable fact
decision's member set. It admits a valid interval only when all supporting
observations agree. Conflicting, unresolved and over-budget support yield
explicit unavailable reasons. No report date or upload date is substituted.

Support traversal checks cancellation and is bounded at 128 members and
256 KiB retained values; incomplete member counts raise an error. This is a
per-fact hydration budget, not a claim about physical engine reads. The
parametrized agreement regression first failed in four of six cases, then
passed. Six additional regressions cover row/byte budgets, duplicate/nonliteral
dates, damaged support membership and cancellation. The focused temporal run
passed 12 tests. OntoScience projects the unavailable reason without defining
another temporal calculation. Accepted ESG temporal extraction, publication-wide
bounds, persisted-operation cancellation, physical reads and App playback remain
unqualified. No persisted schema, dependencies or model execution changed.

Upstream assessment for this correction: no upstream merge was performed;
the fork-specific publication decision graph and worker protocol require these
regressions to be retained when merging native temporal-owner changes.

## Native scene effective-time field contract

The native scene HTTP 500 was caused by this repository's
`PublicationRecords._scene_projection` allowlist. OntoScience sent the typed
relationship projection `id`, `source`, `target`, `predicate`, `status`,
`validTime`; the host DTO validator accepted it, but the native owner rejected
it before the storage query. The allowlist now admits the effective-time field
groups for `links`, `incident`, and `topology`; neighborhood reads normalize to
the same incident owner. Effective-time values are still computed from the
fact's bounded support set above.

The built dev artifact contains this allowlist and has digest
`sha256:205879bcc77d99c2d230f934656d15937881303089e4822181dc99ee5ff51e9d`,
with Semantica source revision `a6a716d2dbedf9c220b1048f901c4c00e2d06203`.
Isolated OntoScience Auto Test run `4cf318a0-9064-47fa-8545-6bdca111f4bc`
loaded that exact artifact and passed both Knowledge Map Cases plus the native
query API contract; all observed scene query responses were HTTP 200. This is
App-level evidence for the field-contract fix, not proof of physical storage
read bounds or the remaining Knowledge Map acceptance gates.

The focused Semantica pytest file was not rerun in this environment: the
canonical checkout's `.venv-page-progress` points into a missing OntoScience
`.tmp` path, and the system Python has no pytest installed. The artifact and
isolated App evidence remain available at the runtime receipt and run paths;
no checkout or generated environment was cleaned or recreated.
