# Keep Full Graph as the initial Explorer view

- Record ID: 2026-11-01-full-graph-default
- Date / author: 2026-11-01 / project contributor
- Status: verified-in-stated-scope
- Fork base revision: bdff5e4b8e03ff16d69ed0797649d4146089cc2a
- Upstream reference: not inspected in this scoped correction
- Related records: existing Explorer graph-filter behavior

## Reason and scope

The user requires Knowledge Map to open in Full Graph. GraphWorkspace starts
with `viewMode = "full"`, but its ready callback overrides that choice when
there are more than 48 nodes and grouping is available. Remove that override.
Preserve explicit Grouped View selection, graph layout, filtering and data.

## Native capability assessment

- Owner: `explorer/src/workspaces/GraphWorkspace/GraphWorkspace.tsx`,
  `GraphWorkspace`, `applyGraphReadySummary`, `setLayoutViewMode`.
- Inspected initial state, ready callback, mode buttons, grouped availability,
  small-graph threshold and `explorer/tests/graphFilters.e2e.ts`.
- Decision: repair the existing owner by deleting automatic mode selection.
  No host injection, new state owner, persistence or second implementation.

## Approach and actual changes

- Extend the existing browser regression to assert Full Graph on large-graph
  load, explicit grouping, return to Full Graph and reload preservation.
- Delete the one-shot automatic grouping effect and its unused ref.
- No API, stored-data, model, network or dependency changes.

## Verification and limitations

- Red: existing browser regression failed before the source fix at
  `large graphs default to Full Graph` (`false !== true`). The fixture contains
  80 nodes, above the 48-node automatic-grouping threshold.
- Green: `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  node --import tsx --test tests/graphFilters.e2e.ts` passed (1/1).
  Covers initial Full Graph, manual Grouped View, return to Full Graph,
  filters and reload. Screenshot reviewed:
  `explorer/test-results/graph-filters-overview.png` (local evidence, not committed).
  Used installed Chrome because Playwright's default browser was not installed.
- `npm run test:graph-workspace`: 165/165 passed.
- `npm run build`: TypeScript and Vite production build passed; Vite reported
  a static/dynamic import overlap warning for `explorationEffectsPluginPhaseC`.
- `git diff --check`: passed.
- Existing OntoScience Case: `page-knowledge-graph`; delta keep, existing
  primary E2E owner retained. Fork browser checks provide supporting evidence.
  No baseline or hard-gate changes.
- Packaged App/artifact publication and host product acceptance not performed.
- Host `change-verification`, guard and typecheck not run: no host files changed.

## Upstream merge assessment

- Disposition: pending incoming upstream review. Preserve explicit user mode
  selection; drop this patch if upstream already defaults to Full Graph without
  size-dependent automatic grouping.
- After merge run the graph-filter browser regression and Explorer build.
