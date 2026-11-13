# Graph workspace density and duplicate status cleanup

- Record ID: 2026-11-13-graph-workspace-density
- Date / author: 2026-11-13 / Codex
- Status: verified-in-stated-scope
- Fork base revision: ec05e559a4bc509c2d2e380b997327238c937d3a
- Upstream reference: not inspected
- Related issue / PR / commits / records: pending commit

## Reason and scope

Knowledge Map's embedded graph presented the same scale information in the
toolbar, filter row, and a persistent layout-status chip. Advanced scope
controls and the semantic legend also consumed canvas-adjacent space even when
unused. The change keeps the graph data and controls intact while making
secondary information explicitly opt-in.

## Native capability assessment

- Existing owner and inspected files/symbols: `explorer/src/workspaces/GraphWorkspace/GraphWorkspace.tsx` (`SemanticColorLegend`, filter row, load status strip) and `explorer/src/NativeScopeControls.tsx` (native scope controls).
- Actual callers / config / exports / tests / recent removals checked: `App.tsx`, graph legend/filter E2E tests, and native scope component tests.
- Decision: repair native owners.
- Evidence no second implementation is introduced: the existing legend, filter controls, and scope controls remain the only owners; only their visibility defaults changed.

## Approach and actual changes

- Changed files and why: graph workspace controls now collapse by default; stable layout no longer emits a persistent status chip or active-node metric; tests explicitly expand controls when exercising them.
- Contract / consumer / stored-data impact and migration or deletion targets: no API, persisted data, or graph contract changes.
- Model / network / dependency / cost impact: none.
- Planned but not implemented: no algorithm or graph rendering changes.

## Verification and limitations

- Commands and results:
  - `npm run test:graph-workspace` — passed (167 tests).
  - `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm run test:graph-filters-e2e` — passed.
  - `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm run test:graph-legend-e2e` — passed.
  - `npm run test:embedded-presentation` — passed.
  - `npm run build` — passed; generated `semantica/static/assets/GraphWorkspace-DDEDCSE2.js`.
  - `npm run lint` — failed on 73 pre-existing repository-wide errors (focused files also surface existing React hook/ref lint findings); no lint finding was introduced in `NativeScopeControls.tsx`.
- Checks not run and why: OntoScience native artifact rebuild and host acceptance are outside this fork checkout and remain required after the immutable pin is updated.
- Known risks / unresolved questions: published native artifact still needs rebuilding and its immutable OntoScience pin must be updated before release use.

## Upstream merge assessment

- Disposition: pending; no upstream revision inspected.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: upstream changes to `GraphWorkspace.tsx` or control styling may overlap.
- Conditions to retain, adapt or remove this change: preserve one owner and re-run graph workspace tests after any merge.

## Dated follow-ups

Focused fork verification is complete. The first Playwright attempt used the default Chromium path, which was unavailable; rerunning with the installed macOS Chrome binary passed. OntoScience artifact publication, pin update, and host acceptance remain the next delivery boundary.
