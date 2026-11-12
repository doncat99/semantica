# Embedded workspace navigation

- Record ID: 2026-11-12-embedded-workspace-navigation
- Date / author: 2026-11-12 / OntoScience contributors
- Status: implemented; focused native-artifact host acceptance passed
- Fork base revision: ea70a1733b133faa4611d99ce9774afd5e7e2188
- Upstream reference: not inspected
- Related issue / PR / commits / records: pending

## Reason and scope

OntoScience already owns project navigation and the Knowledge Map heading.
Embedded Explorer must not repeat its global rail, welcome entry or graph title.
Use one workspace selector while retaining all native workspaces and graph state.
Graph tools, scope controls, Inspector and knowledge computation are unchanged.

## Native capability assessment

- Owner: explorer/src/App.tsx, WorkspaceShell, switchWorkspace, switchExploreView.
- Callers: main.tsx initializes the validated embeddedPresentation bridge before App.
- Decision: repair native owner; no host navigation proxy or CSS hiding of the rail.
- The standalone Explorer retains its existing navigation.

## Approach and actual changes

- Embedded selector replaces rail and Explore tabs; subordinate professional tabs remain.
- One retained GraphWorkspace preserves its selection, filters and viewport.
- Confirmed draft discard resets that graph; rejected navigation keeps the draft.
- No stored-data migration, model call, new dependency or semantic contract change.
- Host consumes a complete make dev snapshot artifact, not the live checkout.

## Verification and limitations

- Explorer TypeScript and Vite production build passed.
- Existing graph-workspace regression suite: 167 passed.
- Embedded navigation source-boundary specifications: 2 passed (red before fix).
- Compiled Explorer Playwright navigation test: passed at 1440px and 760px;
  one retained canvas, preserved search/filter, keyboard return, no page errors.
- Host presentation component suite: 4 passed, including custom-theme color-mix
  normalization in the host presentation owner.
- Product primary owner: e2e/ui/knowledge-secondary-states.test.ts.
- Complete native artifact build and native acceptance passed; bundle digest
  sha256:d6ab64590f2a9c50538b34801b4985469031eeaa55902e870ac7a9a8374bda6c.
  Both host Map Cases passed with this artifact, including workspace retention
  and project resets. Published pin is unchanged; this is a local dev delivery.
- Full change-verification remains blocked by source-revision preparation checks.
  Repository guard is separately blocked by unrelated scratch files. No packaged
  release acceptance is claimed. The user App is open but awaiting onboarding.
- Full host theme/language and dirty-draft interaction coverage remains pending.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not reviewed.
- Overlap: App workspace composition and navigation.
- Recheck embedded and standalone navigation, draft guard and retained graph state.

## Dated follow-ups

2026-11-13: native owner implemented. Complete local worker build started with
uv 0.9.10. Reused checksum-verified pinned Python/model input cache; application
code is rebuilt from the current frozen source snapshot, never copied from an
old worker. Runtime source App.tsx and embeddedPresentation.css are unchanged
after that snapshot; this record is updated separately with actual evidence.

2026-11-13, compact heading follow-up: the user approved removing the host's
separate Knowledge Map title/project subtitle band. The existing embedded nav
now owns a semantic h1 on its left, with the workspace selector on the right.
App.tsx and embeddedPresentation.css remain the only native layout owners;
standalone navigation, graph state and draft handling are unchanged. The old
host header is deleted, not hidden. The existing boundary spec failed before
the change because the compact heading was absent. Compiled browser coverage
now checks same-row alignment and nonoverlap at desktop and narrow widths.
Native-artifact build and acceptance passed for this follow-up; bundle digest
sha256:dc50b7a71506f80b344fd7fc85dc02aaec1ba6fc358a64d93eabf3ecb62e7f85.
Both host Map Cases passed with the complete artifact. Explorer build, boundary
specs (2/2), compiled desktop/narrow browser test, host presentation tests (4/4)
and host web typecheck passed. Fresh host evidence is under host
.tmp/map-navigation-focused/evidence/compact-heading/.
Full change-verification failed in the separate Explore canvas test with a
Chromium target crash; remaining UI tests did not run. User desktop was restarted
with this artifact but requires login. No published pin, packaged qualification
or baseline promotion is claimed. No data migration is needed.
Upstream merge overlap remains App composition and embedded styling.
