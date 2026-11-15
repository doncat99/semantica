# Knowledge Map Analyze relation selection

- Record ID: 2026-11-15-knowledge-map-analyze-relations
- Date / author: 2026-11-15 / Codex
- Status: implemented in canonical source checkout; OntoScience artifact integration pending
- Fork base revision: `4ece1d8ca54afb4e1b3bf9fd6d00d80df5662835`
- Upstream reference: not inspected
- Related issue / PR / commits / records: Knowledge Map Analyze UI request

## Reason and scope

Analyze currently converts every graph edge into `predicate(sourceId, targetId)` and places all facts into a textarea. Users see opaque IDs and cannot select a bounded relation set. The GraphWorkspace stays mounted to preserve graph state, but its timeline is always rendered and temporal requests remain enabled when another workspace is active.

## Native capability assessment

- Existing owner and inspected files/symbols: `semantica/explorer/routes/enrich.py::graph_reasoning_facts`; `GraphSession.iter_edges` / `normalize_edge`; `ContextGraph.find_edges(skip, limit)`; `explorer/src/workspaces/ReasoningWorkspace.tsx`; `explorer/src/workspaces/GraphWorkspace/GraphWorkspace.tsx` temporal lifecycle.
- Actual callers / config / exports / tests / recent removals checked: `ReasoningWorkspace` is the `/api/reason/facts` caller; `ContextGraph.find_edges` supports bounded raw edge pages and `edge_type_index` is maintained by the graph owner; existing temporal lifecycle tests cover request guards.
- Decision: repair native Explorer owner and its current callers.
- Evidence no second implementation is introduced: keep the same reasoning route and GraphWorkspace; add pagination/labels to the current route and active-state gating to current temporal effects.

## Approach and actual changes

- Changed files and why: `explorer/src/App.tsx` and `explorer/src/workspaces/GraphWorkspace/GraphWorkspace.tsx` pass the active workspace state to the retained graph and hide the timeline while inactive. Temporal lifecycle predicates and requests now stop/abort on deactivation. `explorer/src/workspaces/ReasoningWorkspace.tsx` presents readable, selectable relationship rows, filters by relation type, and requests bounded pages. `semantica/explorer/routes/enrich.py` owns the paged relationship projection; tests cover the contract and temporal lifecycle. The Explorer workspace test command now includes its relationship-selection test. OntoScience's existing `page-knowledge-map` Case and UI journey were updated to verify the user-visible behavior.
- Contract / consumer / stored-data impact and migration or deletion targets: `/api/reason/facts` now returns a bounded page of labeled relations, relationship-type counts, and paging metadata instead of the old unbounded `facts` array. The only production caller is `ReasoningWorkspace`; its reasoning submission continues to use stable graph IDs internally. No stored data changes or migration are intended.
- Model / network / dependency / cost impact: no model calls or new dependencies; bounded 100-row pages.
- Planned but not implemented: none known.

## Verification and limitations

- Commands and results: `npm run build --prefix explorer` passed; `npm run test:graph-workspace --prefix explorer` passed (170 tests); `.venv/bin/python -m pytest tests/explorer/test_workspace_data.py tests/explorer/test_explorer_api.py -q` passed (141 tests); main-repository catalog JSON parse and `git diff --check` passed.
- Checks not run and why: the main-repository Playwright journey was not run because no tools-dev runtime was running and the currently pinned OntoScience Semantica artifact does not include this checkout's changes. The journey needs a qualified artifact or the documented local `make dev` artifact build before it can verify the packaged product path.
- Known risks / unresolved questions: the OntoScience release pin remains immutable and does not include local fork changes until a qualified artifact is published and pinned. This source-checkout result is not evidence that an installed or packaged OntoScience app contains the change.

## Upstream merge assessment

- Disposition: pending.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: upstream may change Explorer workspace navigation or temporal lifecycle.
- Conditions to retain, adapt or remove this change: compare route and GraphWorkspace owner before any upstream merge.

## Dated follow-ups

2026-11-15: Implemented the canonical Explorer source and updated the existing OntoScience `page-knowledge-map` Case. Focused source/API and workspace checks pass. No external commit, artifact publication, OntoScience pin update, packaged build, or real-app journey has been performed.
