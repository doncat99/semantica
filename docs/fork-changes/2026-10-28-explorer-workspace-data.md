# Explorer workspace data completion

- Date: 2026-10-28
- Status: planned
- Fork base: 53a860172d52efdfd7e7315dc8313516f0cf144b

## Native capability assessment

Inspected GraphSession.from_file, ContextGraph.record_decision/save_to_file,
routes/decisions.py, routes/enrich.py, DecisionWorkspace and ReasoningWorkspace.
Decisions has read routes only; ContextGraph already owns decision creation.
ReasoningWorkspace defaults to drug examples despite having a loaded graph.
Reuse those owners, with no new inference algorithm or synthetic decisions.

## Approach

Expose native decision recording with validated fields and graph facts for reasoning.
Persist a mutable Explorer sibling of the immutable graph input. Reload that
workspace on restart. Preserve native UI classes and navigation.

## Verification and limitations

Red specifications: tests/explorer/test_workspace_data.py.
Verification pending. No model or network calls introduced.
Upstream assessment pending; retain only while upstream lacks these native flows.

## 2026-10-28 implemented and verified assessment

Status: implemented. Reasoning now loads facts from the active graph, keeps rules
empty and examples optional. SPARQL runs the existing All triples query on entry.
Lineage selects a current graph node and offers a node list. Decisions exposes
ContextGraph.record_decision through the native API and form, validates related
entities, and saves an atomic Explorer working copy beside the immutable input.
GraphSession reloads that working copy after restart.

Checks: explorer production build passed; graph-workspace tests 162 passed;
workspaceData.test.tsx 2 passed; Python Explorer suite 379 passed, 5 skipped,
1 deselected (semantica_mcp is absent; deterministic rendering E2E excluded).
Native bundle acceptance passed. Browser checks against the relocated bundle
and an isolated copy of a real 431-node / 14933-edge graph confirmed current
reasoning facts, 20 SPARQL result rows, automatic lineage selection, populated
KG Overview, and decision creation plus reload. No test decisions were written
to the original graph. Restart persistence is covered by test_workspace_data.py.

Limits: 6 real graph edges cannot use the existing reasoning syntax and are
reported as skipped. Rules, imports and dedup scans still require explicit user
input. Empty decision data remains empty until a real decision is recorded.
Incoming upstream comparison remains pending; this assessment covers the fork
base above, not an uninspected newer upstream revision.

## 2026-10-29 pre-push verification

Re-ran workspaceData.test.tsx: 2 passed; Explorer `tsc -b` passed. The combined
Python checkpoint/query/Explorer workspace/PDF ownership selection passed all
91 tests. No new browser or full native artifact acceptance was run in this
verification; prior browser evidence and limitations remain as recorded above.
