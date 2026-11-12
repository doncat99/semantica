# Explorer host presentation

- Date: 2026-11-12
- Status: implemented locally; artifact delivery pending
- Fork base revision: a8afb9945153745f20d5e4b1f793ee68fe14acb5
- Upstream reference: not refreshed; merge assessment pending

## Reason and native capability assessment

Embedded Explorer ignores the host theme. App shellStyles, index.css and
GraphWorkspace/graphTheme.ts own separate hardcoded dark surfaces. GraphCanvas
and sigmaNativeRendering consume literal theme colors, so iframe CSS alone
cannot align the canvas. Repair these existing presentation owners; retain
native loading, graph store, reducers, layouts, interaction and semantic colors.
Callers inspected: GraphWorkspace, GraphInspectorPanel, TimelinePanel,
MarkdownContentViewer, MemoryWorkspace, NativeScopeControls, graphColorLegend.e2e.

## Approach and consumer impact

The host supplies resolved color/font tokens in the initial iframe URL and
live origin/source-bound presentation messages. Native validation accepts only
the current complete presentation shape. DOM uses theme CSS variables; canvas
uses resolved literal colors and refreshes the same renderer. No graph reload,
model call, persistence or knowledge schema change. No superseded graph path
or migration/deletion target; standalone presentation remains the same owner.

## Verification and limitations

Host component tests 3/3 and web typecheck passed. Native graph-workspace tests
167/167 and production build passed (existing mixed dynamic/static import
warning remains). Final native browser regression passed with light/dark/narrow
screenshots and Canvas pixel checks, preserving the renderer, selected node,
coordinates, semantic colors and graph request count during live theme updates.
Wrong-origin, non-parent and malformed updates are rejected. Two earlier browser
runs timed out during graph loading under high concurrent machine load; the
final pass used the same 30-second timeout and no intervening product fix.

Screenshots under ignored `explorer/test-results/host-presentation-*.png` were
visually inspected. Route-mocked browser data is not packaged acceptance or
real-corpus evidence. Host change-verification was blocked before execution by
isolated tools-dev startup, run `6d71c269-eb69-44a8-a402-5f86a4937992`.
Complete App artifact delivery remains pending. Host downloadable font files
are not shared: the requested font stack uses installed/system fallbacks.

## Upstream merge assessment

Pending incoming upstream review. Reconcile with App/graphTheme native owners
if upstream adds equivalent embedding support; do not retain parallel bridges.
Recheck origin validation, live canvas/theme switching and state preservation.

## 2026-11-12 follow-up: duplicate graph counts

The native GraphWorkspace toolbar rendered a node/edge summary above the
filter row, which already reports visible/total nodes and relationships.
Removed only the toolbar summary MetricChip; loading, active-node and focus
status remain. No graph/data contract or migration change. The existing browser
regression first failed because the duplicate count was present (1 instead of
0), then passed after removal, also asserting the lower visible/total status.
Light/dark/narrow screenshots were refreshed. These local evidence files are
untracked, not ignored; do not include generated screenshots in the source commit.
Upstream merges should preserve a single visible/total count owner in the
filter row rather than restore the redundant toolbar summary.
