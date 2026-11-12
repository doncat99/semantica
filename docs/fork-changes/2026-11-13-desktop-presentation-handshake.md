# Desktop embedded presentation authentication

- Record ID: 2026-11-13-desktop-presentation-handshake
- Date / author: 2026-11-13 / Codex
- Status: verified in the stated scope; real-project desktop acceptance pending
- Fork base revision: fae75885541b54130c68fe889b410a7b42742801
- Upstream reference: not inspected
- Related issue: OntoScience Knowledge Map cannot open in packaged desktop

## Reason and scope

Actual packaged Electron probe: an HTTP iframe embedded by ontoscience://app
has an empty document.referrer even with referrerPolicy=origin. The existing
mandatory Referrer check throws before rendering the Explorer or reading data.

## Native capability assessment

- Owner: explorer/src/embeddedPresentation.ts and explorer/src/main.tsx.
- Consumer: OntoScience SemanticaExplorer iframe onLoad and theme updates.
- Decision: repair the native initializer; no second renderer or theme owner.

## Approach and actual changes

Authenticate presentation using MessageEvent.origin and the actual parent
WindowProxy. Wait for the parent's presentation before rendering, with a bounded
timeout. Remove the Referrer dependency and URL-carried initial presentation.
No stored-data migration, model calls or additional network requests.

## Verification and limitations

- Red specification reproduced `Invalid Explorer presentation parent` before
  the fix. `npm run test:embedded-presentation`: 1/1 passed after the fix,
  including wrong-origin/source rejection, malformed input and live updates.
- `npm run test:graph-workspace`: 167/167 passed; `npm run build` passed.
- `CHROMIUM_PATH=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  npm run test:graph-legend-e2e`: passed with no-referrer embedding, light/dark
  Canvas pixel checks, retained selection/coordinates and narrow screenshots.
- Actual Electron probes confirmed empty Referrer and authenticated parent
  MessageEvent.origin `ontoscience://app` with event.source === window.parent.
- Complete local native bundle acceptance passed. OntoScience packaged the
  artifact digest sha256:e3cd6a0d28a0c43ea613354c2295d549a38bd71a21e4d9c631f67694aa8fced6
  and launched local version 0.10.0-local.20261112.184531Z.
- Host focused suite: 4/4 passed; host web typecheck passed. Full-repo typecheck
  failed in an unrelated native-understanding test (missing jobId). Local
  experience packaging explicitly used RELEASE_VERIFY=0, not a release pass.
- Affected change-verification run 4f8f3a09-b950-4641-b59e-c6e78d9661dc
  failed on an unrelated Explore browser crash before the Map cases ran.
- Real user graph acceptance requires completing the desktop onboarding flow;
  no synthetic user-profile mutations or account-gate bypass were performed.
- This record was updated after artifact snapshotting; it is not a claim that
  the built artifact contains this final documentation revision.

## Upstream merge assessment

- Disposition: pending; upstream not reviewed.
- Owner overlap: embeddedPresentation initializer and main entry.
- Retain only while native embedding needs authenticated presentation messages.
- Rerun desktop no-Referrer, origin/source rejection and graph rendering checks.
