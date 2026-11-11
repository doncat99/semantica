# Explorer scope entry and bounded link pages

- Date / author: 2026-11-12 / Codex
- Status: implemented; local artifact qualification pending
- Fork base revision: b877493dfc538f217241635cb0c8849140cfd759
- Upstream reference: semantica-agi/semantica 2c6cfefcabe3c02c90df915a8de463d43f5691e6

## Reason and native capability assessment

Repair `NativeScope.select` (`semantica/explorer/native_scope.py`) and its
`explorer/src/NativeScopeControls.tsx` caller. The native publication relay
already supports projected link pages bound to visible node identities and an
`after` cursor. Current selection rejects that continuation instead of exposing
it. The empty controls also require choosing an item before any action is enabled.
Inspected the existing Python and component tests and App remount/cache owner.
No second graph, storage owner or automatic whole-project traversal is needed.

## Approach and consumer boundary

Preselect the first item in the bounded source catalog and explain the empty
state with an enabled Open scope action. Add `linksAfter` to the existing scope
selection and `link_next_cursor` to its response. Re-read the same node page and
replace, never append, its visible link page. Node navigation resets link
navigation. Retain cancellation, atomic install, project/generation validation,
128 node/link and 256 KiB scene budgets. No model calls or stored-data changes.
Delete the continuation rejection and its obsolete test expectation.

OntoScience consumers are the pinned native App (UI and CLI share its launcher),
the two Knowledge Map browser Cases and the capability registry. Search latency,
publication rebuilds, classification and real-user writes are out of scope.

## Verification and limitations

Pending red regressions, focused tests, frontend build, immutable native artifact
qualification and host acceptance. Source tests alone do not qualify the App.

## Upstream merge assessment

Pending, incoming upstream not reviewed. Keep only while native Explorer scope
controls lack equivalent bounded link navigation; recheck scope, cancellation,
byte limits and UI cache invalidation on merge.

## Corrected product behavior and history audit

The first-source proposal above was rejected before implementation. Selecting a
Project is already the scope choice. Upstream initializes GraphSession from its
input and automatically loads nodes and edges. Fork commit
52fa9451cf1ab863c560c342f047ad49be66916d introduced the empty native session and
manual selection gate; bf0b71be retained it. There is no upstream requirement
to choose a source before seeing a Project graph.

Native startup now selects the bound Project with an empty filter, reads its
first bounded node/link page, and opens the graph workspace. Sources, Themes and
communities remain optional filters. Project graph returns to the unfiltered
first page. Node and link navigation replace pages and expose continuation;
neither startup nor navigation accumulates a full Project in memory. Failed
startup fails explicitly; cancellation retains atomic scene installation.

Red specifications reproduced three Python failures (manual startup, link
overflow, cursor validation) and the missing link navigation in the component.
The first green run passed all nine native-scope checks and 167 frontend workspace
checks. Added startup-failure and Project reset coverage before final verification.
Immutable bundle qualification and isolated host browser acceptance are recorded
in the OntoScience handoff; no release qualification is inferred from unit tests.

## Final correction: automatic native graph loading

The first-page and user pagination design above was also rejected. Upstream's
`useLoadGraph.ts` consumes all node and edge cursors automatically. Bounded
transport is not a requirement for user-facing graph pages. The current
implementation removes graph pagination, automatically traverses the complete
bound Project (nodes then projected topology), and installs one native graph.
Optional filtered scopes consume link continuations internally; scopes over 128
nodes use indexed incident pages and deduplicate by fact identity, preserving
cross-batch edges and status. Catalog browsing remains separate from graph loading.

Native layout/algorithms require the graph in memory. Individual owner reads stay
at 128 rows (32 for incident), 256 KiB; cumulative projected input is limited to
128 MiB and loading to 300 seconds. Exceeding either fails explicitly and leaves
the previous session installed, never a partial Project. This is an Explorer
resource limit, not a publication or persistent graph-size limit. No data writes,
models, rebuilds or search changes. Qualification below must use the final source
snapshot; earlier pagination build candidates are superseded.

## Final verification, 2026-11-12

Final source passed 81 storage/Explorer Python tests, 167 frontend workspace
tests and the TypeScript/Vite build. OntoScience's 76 focused relay/Explorer
checks and daemon typecheck passed. The complete local native artifact passed
its relocated acceptance with digest
`sha256:195d81f2ecbfa36e7582bd2fc4feb5889acdd42057bfa42da58ed5fdd8ffe094`.
This qualifies the local source artifact, not a published release pin.
Host browser assertions were blocked by route warmup timeout; combined
change-verification was rejected because source changed after preparation.
Real ESG full-graph rendering, native heap usage and the host's 60-second startup
deadline remain unverified. No baseline or acceptance budget was relaxed.
