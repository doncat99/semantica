# Align Embedded Explorer Controls With Host Tokens

- Record ID: 2026-11-13-embedded-explorer-controls
- Date / author: 2026-11-13 / Codex
- Status: implemented-verified
- Fork base revision: `5d422d84eedc717a79399c9d2fc6ce8849bae8db`
- Upstream reference: not inspected for this change
- Related issue / PR / commits / records: pending

## Reason and scope

Knowledge Map embeds the native Explorer in an iframe and sends host presentation tokens. Its GraphWorkspace search, mode, toolbar, filter and inspector surfaces kept independent gradients, shadows, large radii and hover motion, so the visible controls did not match OntoScience's compact application UI. Keep graph semantics and navigation unchanged; normalize those existing surfaces only when host presentation is active.

## Native capability assessment

- Existing owner and inspected files: `explorer/src/embeddedPresentation.ts`, `explorer/src/embeddedPresentation.css`, `explorer/src/workspaces/GraphWorkspace/GraphWorkspace.tsx`.
- Actual callers / config / exports / tests / recent removals checked: the host iframe initializes the existing presentation bridge; the GraphWorkspace controls are rendered by its existing owner; `explorer/tests/embeddedPresentation.test.ts` covers parent-message authentication.
- Decision: repair native owner.
- Evidence no second implementation is introduced: the patch extends the existing host-presentation stylesheet and does not add components, runtime messages or alternate render paths.

## Approach and actual changes

- Changed files and why: `explorer/src/embeddedPresentation.css` maps existing graph controls to host surface, border, accent and text tokens; `explorer/tests/embeddedPresentation.test.ts` remains the bridge unit owner; host E2E assertions in OntoScience check computed iframe styles.
- Contract / consumer / stored-data impact and migration or deletion targets: visual-only; no contract or persisted data changes.
- Model / network / dependency / cost impact: none.
- Planned but not implemented: none.

## Verification and limitations

- Commands and results: Semantica bundle build and native worker acceptance passed; OntoScience `pnpm tools-test run --plan change-verification --flow knowledge-map-native` passed on Auto Test run `65b7a827-774b-4bfb-8253-359ad7d8f57e`. Both `page-knowledge-map` and `page-knowledge-map-project` passed with no hard-gate issues. The real embedded Explorer request returned HTTP 200; the 2-node/1-link canvas rendered; computed focus styles showed one 1px host-accent border with no container shadow/outline and no input outline. Project switching cleared search and filters.
- Artifact evidence: `sha256:0566fad7267cbbb3fd86441a747de929546d03f9be61da5407f09b61865fd0f9`.
- Checks not run and why: standalone Explorer presentation is intentionally outside the embedded-host change.
- Known risks / unresolved questions: validation used deterministic two-node publications and confirms rendering/integration, not extraction quality on a real corpus.

## Upstream merge assessment

- Disposition: pending; the upstream presentation owner was not reviewed for this change.
- Incoming upstream revision reviewed: not yet reviewed.
- Overlapping native owners / likely conflicts: upstream may edit `embeddedPresentation.css`.
- Conditions to retain, adapt or remove this change: compare upstream embedded presentation styling and retain only host-specific rules not supplied by the upstream owner.
- Required consumer/regression checks after merge: embedded presentation tests and OntoScience `page-knowledge-map` / `page-knowledge-map-project` acceptance.

## Dated follow-ups

- 2026-11-13: implementation started from inspected fork revision `5d422d84`; final verification status to be appended after checks.
- 2026-11-13: verified the host presentation with Auto Test run `65b7a827-774b-4bfb-8253-359ad7d8f57e`; both Knowledge Map P1 Cases passed and the built bundle digest was `0566fad7267cbbb3fd86441a747de929546d03f9be61da5407f09b61865fd0f9`.
