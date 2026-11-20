# Restore standalone Explorer UI to upstream

- Record ID: 2026-11-20-explorer-ui-upstream-alignment
- Date / author: 2026-11-20 / Codex
- Status: implemented-verified
- Fork base revision: a6a716d2dbedf9c220b1048f901c4c00e2d06203
- Upstream reference: upstream/main 4d83266ca0d7f70185906bfce7c96ec71c6ebc04
- Related issue / PR / commits / records: replaces the UI-only direction in `2026-11-19-graph-workbench-density.md`; no commit created

## Reason and scope

The Semantica fork had accumulated Explorer UI changes for OntoScience embedding,
presentation density, graph filters, and related workspace presentation. Those
changes coupled OntoScience UI iterations to Semantica's Explorer source and its
built artifact. The requested boundary is for OntoScience to own its Sigma
Knowledge Map UI while Semantica's standalone Explorer follows upstream.

Scope is the `explorer/` source, tests, package metadata, and README only. Native
Semantica query owners and all other existing fork worktree changes are outside
this restoration and must remain intact.

## Native capability assessment

- Existing owner and inspected files/symbols: upstream standalone Explorer at
  `upstream/main:explorer/src/App.tsx` and
  `upstream/main:explorer/src/workspaces/GraphWorkspace/GraphWorkspace.tsx`.
- Actual callers / config / exports / tests / recent removals checked: compared
  the complete `explorer/` tree at fork `HEAD` and upstream `main`; inspected
  `explorer/package.json`, app entry points, graph loader, and fork history.
- Decision: drop fork-only Explorer UI and use the upstream owner verbatim.
- Evidence no second implementation is introduced: OntoScience's native
  `KnowledgeMapCanvas.tsx` is independently implemented with Sigma/Graphology
  and consumes OntoScience contracts. This change does not modify or import it
  from Semantica.

## Approach and actual changes

- Changed files and why: synchronized all 131 files under `explorer/` to the
  inspected upstream tree; removed fork-only embedded presentation, native
  scope controls, graph filters, tests, and the untracked graph workbench E2E.
- Contract / consumer / stored-data impact and migration or deletion targets:
  removes the Explorer host-presentation/postMessage additions and custom
  graph-filter UI. Native Python APIs, OntoScience HTTP/CLI contracts, and data
  are unchanged. Generated `semantica/static` output is outside the source
  alignment; it was regenerated locally by the production build used for
  verification, as detailed below, and is not a release artifact.
- Model / network / dependency / cost impact: no model or runtime dependency
  behavior change; Explorer package metadata now matches upstream.
- Planned but not implemented: no migration of the remaining OntoScience
  Explorer-session owner or its consumers is included in this UI alignment.

## Verification and limitations

- Commands and results: `npm run test:graph-workspace` passed (162 tests);
  `npm run build` passed (`tsc -b` and Vite production build); and
  `git diff --quiet upstream/main -- explorer` confirmed the complete source
  tree matches upstream reference `4d83266ca0d7f70185906bfce7c96ec71c6ebc04`.
- Checks not run and why: no standalone App runtime was launched, and no
  immutable Semantica artifact was built or qualified. Explorer lint and other
  unrelated workspace suites were not run.
- Known risks / unresolved questions: build output is configured to the ignored
  `semantica/static/` directory, so the local generated bundle was updated by
  the verification build. This directory was absent from the initial Git
  status and its prior contents could not be established, so it was preserved
  rather than guessed at or deleted. The build is not a published or immutable
  release artifact. The standalone upstream Explorer still needs runtime
  compatibility validation against the fork's current backend before any
  artifact is promoted.

## Upstream merge assessment

- Disposition: drop; fork-only UI changes now match upstream `main` exactly.
- Incoming upstream revision reviewed: `4d83266ca0d7f70185906bfce7c96ec71c6ebc04`.
- Overlapping native owners / likely conflicts: native backend query owners are
  outside `explorer/`; future backend protocol differences require separate
  owner-level compatibility evidence.
- Conditions to retain, adapt or remove this change: keep standalone Explorer
  source aligned to upstream; implement Knowledge Map presentation changes in
  OntoScience's owner.
- Required consumer/regression checks after merge: Explorer build and upstream
  focused workspace tests; separately verify OntoScience's Sigma surface.

## Dated follow-ups

### 2026-11-20 verification

- Source alignment is verified against the recorded upstream commit; all 162
  focused graph workspace tests pass and the Explorer production build passes.
- The build writes to ignored `semantica/static/`; this local output was
  regenerated during verification and is not evidence of a fixed or published
  artifact. No Semantica release package was created or published.

