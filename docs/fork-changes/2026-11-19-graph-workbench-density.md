# Graph workbench density and temporal visibility

- Record ID: 2026-11-19-graph-workbench-density
- Date / author: 2026-11-19 / Codex
- Status: implemented
- Fork base revision: a6a716d2dbedf9c220b1048f901c4c00e2d06203
- Upstream reference: not inspected
- Related issue / PR / commits / records: pending

## Reason and scope

OntoScience's embedded graph spends excessive height on six expanded tool groups
and an empty temporal footer. Restore graph mode to the native center toolbar,
keep camera/layout visible and disclose secondary analysis tools on demand.

## Native capability assessment

- Owners: GraphWorkspace.tsx ToolbarCluster, SegmentedModeControl and footer;
  TimelinePanel.tsx; embeddedPresentation.css. Native get_temporal_bounds in
  semantica/explorer/session.py reads node AND relationship valid_from/valid_until.
- Consumers: App.tsx embedded GraphWorkspace; OntoScience KnowledgeMapRoute.
- Decision: repair existing native owners, remove host mode presentation.
- Existing temporal lifecycle, graph filter and embedded navigation tests checked.
  No alternate graph state, temporal inference or processing owner is introduced.

## Approach and actual changes

Implemented: compact primary toolbar with Camera and Layout kept visible;
secondary Local, Distance, Analysis and Utility groups are disclosed on demand;
the native Graph view mode remains in the center toolbar; and the temporal footer
is rendered only after real node or relationship validity bounds are available.
No persisted data migration, dependency, model call or processing cost change.

## Verification and limitations

Focused browser check: `explorer/tests/graphWorkbench.e2e.ts` passes with mocked
undated and dated graph lifecycles, including playback and pause behavior,
toolbar disclosure and narrow viewport overflow checks. Real ESG corpus validity
metadata and installed App acceptance are not established by browser fixtures.

## Upstream merge assessment

Re-evaluate toolbar ownership and temporal visibility on future merges.

## Dated follow-ups

