# Embedded workspace theme and scroll

- Record ID: 2026-11-19-embedded-workspace-theme-and-scroll
- Date / author: 2026-11-19 / OntoScience
- Status: verified-in-stated-scope
- Fork base revision: de635ca2360dc72247f3a3cb898b26b2d30f5817
- Upstream reference: not inspected for this UI repair
- Related issue / PR / commits / records: OntoScience Knowledge Map embedded presentation; commit pending

## Reason and scope

The embedded Explorer's Graph controls used host presentation tokens, while Vocabulary and several sibling workspaces retained dark backgrounds and pale text. Vocabulary's react-arborist tree also used a fixed 600 px viewport, hiding its end rows in a shorter App window. The native Explorer owns these pages and their scroll containers. The work changes presentation and layout only; SKOS data, graph semantics, and user materials are unchanged.

## Native capability assessment

- Existing owner and inspected files/symbols: `explorer/src/App.tsx` workspace shell and shared tokens, `explorer/src/embeddedPresentation.ts`, native workspace components, `VocabularyWorkspace/ConceptTree.tsx`, `OntologyWorkspace/ontologyEditorModel.ts`.
- Actual callers / config / exports / tests / recent removals checked: embedded parent presentation message, workspace selector, Vocabulary query hooks, React Arborist viewport, ontology MiniMap, `explorer/tests/embeddedNavigation.e2e.ts` and `ontologyEditorModel.test.ts`.
- Decision: repair the existing native owner.
- Evidence no second implementation is introduced: the same workspace components and host message contract remain in use; no host CSS overlay, data adapter, or alternate page was added.

## Approach and actual changes

- Changed files and why: replace fixed decorative workspace surfaces and text with existing `--ws-*` presentation tokens; derive semantic status text from host contrast; follow host tokens in SPARQL Monaco and ontology MiniMap; size the Vocabulary tree from its container with `ResizeObserver`; allow Vocabulary detail scrolling and narrow layout. Add native browser and unit assertions.
- Contract / consumer / stored-data impact and migration or deletion targets: presentation-only; no API, stored-data, or migration change. The fixed-height tree and dark MiniMap styling are replaced in place.
- Model / network / dependency / cost impact: none; no model calls, new network requests, or dependencies.
- Planned but not implemented: no redesign of the standalone Explorer or semantic graph palette.

## Verification and limitations

- Commands and results: `npm run build` passed; `node --import tsx --test tests/ontologyEditorModel.test.ts tests/embeddedPresentation.test.ts` passed 8/8; `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node --import tsx --test tests/embeddedNavigation.e2e.ts` passed after the source fix, checking light/dark surfaces and final tree row at 1200x620 and 760x480. Before the fix, the same theme assertion failed: expected light host surface, actual dark `rgb(13,17,23)`. Browser screenshots are under ignored `explorer/test-results/`.
- Checks not run and why: full app acceptance and published-artifact verification are separate integration steps.
- Known risks / unresolved questions: semantic colors in standalone Explorer remain its existing palette; individual non-Vocabulary forms require App-level visual inspection with representative data.

## Upstream merge assessment

- Disposition: pending until an incoming upstream revision is inspected.
- Incoming upstream revision reviewed: none.
- Overlapping native owners / likely conflicts: Explorer workspace styling, embedded presentation and Vocabulary layout.
- Conditions to retain, adapt or remove this change: remove when upstream provides host-token presentation and container-sized Vocabulary tree with equivalent tests.
- Required consumer/regression checks after merge: native build, embedded presentation and navigation tests, OntoScience Knowledge Map UI Case.

## Dated follow-ups

None.
