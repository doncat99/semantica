# Explorer complete Project startup traversal

## Reason and inspected native owner

At inspected revision 3d50712d7b4aea5b49a9bbbfb0c414581cb198de,
Explorer NativeScope.select loaded each node page using a separate sorted
PublicationRecords.scene query before Uvicorn startup. An isolated backup of
the ready ESG publication took 92.28 seconds for 25,286 nodes and 27,111 edges;
OntoScience terminated startup after 20 seconds. Python imports took 2.59 seconds.
This integration path was introduced before the three-column presentation work.

Native owner: semantica/semantic_query.py::NativeTraversal already maintains one
query iterator and bounded lookahead per traversal. PublicationRecords.scene
already accepts that traversal. No alternate graph/query engine is needed.

## Implementation and callers

NativeScope.select now uses NativeTraversal for complete Project nodes and
topology, through NativeScope.page, retaining admission checks at every page.
The existing filtered selection path and original GraphSession are unchanged.
Each traversal is local to one selection and released on completion/failure;
no source data, publication or knowledge identity is rewritten. Existing row,
byte, time, cancellation and generation checks remain. The CLI emits the native
loading stage before starting the complete scene read.

OntoScience must allow the existing native 300-second scene budget plus Python
startup; health still means the entire scene was installed, never an empty graph.
Its publication fence must not be swallowed by the health probe's network catch.

## Regression evidence

- New failing-before-fix test in tests/explorer/test_native_scope.py verifies
  one native traversal across node pages and a distinct topology traversal.
- Existing mocks accept the delegated traversal; filtered selection expectations,
  cancellation, failed continuation, limits, and native types remain covered.
- `.venv/bin/python -B -m pytest -q tests/test_native_record_worker.py tests/explorer/test_native_scope.py tests/explorer/test_native_admission.py`: 45 passed.
- Same isolated ESG backup, complete NativeScope.select: 19.05 seconds,
  25,286 nodes and 27,111 edges. No model/network calls or truncation.
- Packaged App acceptance is owned by the accompanying OntoScience delivery;
  source timing alone does not establish packaged user acceptance.

## Limits and upstream assessment

The existing in-memory Explorer scene budget remains 128 MiB and 300 seconds;
this change does not claim unbounded graph capacity or redesign native Explorer.
Upstream assessment: keep native traversal reuse; adapt if upstream replaces
NativeTraversal or the scene contract. No fallback or compatibility reader added.

## Embedded presentation follow-up

The native Explorer presentation owner is restored from fork history and binds
host colors/font before rendering. Global resets remain scoped to the Explorer
mount. The packaged CSP rejects remote Google Fonts imports, so the stylesheet
uses installed/host fonts without a remote import; the CSP is unchanged.
Actual three-column inspection exposed viewport breakpoints selecting desktop
layouts for a narrow embedded panel. App and GraphWorkspace now use the named
Explorer inline-size container with their existing breakpoints and rules.
The landing page also consumes host palette/font tokens. No navigation, API,
graph query, publication, or backend lifecycle behavior is changed by this UI
follow-up. OntoScience mirrors these native files with provenance hashes.
Focused host navigation/route checks and packaged acceptance are recorded in
OntoScience's accompanying knowledge-map-publication-readiness-20261122.md.

Electron inspection also exposed flex shrinking the wrapped workspace header
below its content height. The native header now keeps its intrinsic height
(`flex-shrink: 0`), so the graph body starts after the tabs instead of overlapping.


## Correction: service and Project lifecycles

The earlier startup traversal integration coupled child-process readiness to a
specific Project. The native owner now also supports an unbound host-managed
service (`--native-service`). It admits the host pipe, starts HTTP/WebSocket
health without opening a store, and accepts only the private
`X-Explorer-Control-Key` management channel for binding `{path, projectId,
generation, apiKey, origin}`. Binding uses the existing `NativeScope` and
`GraphSession`; DELETE closes that scope and revokes the session while keeping
the process alive. A host cancel signal reaches the existing cancellation
event. Dynamic origin and API-key checks fence HTTP and WebSocket requests;
active requests drain for at most five seconds before cancellation, preventing a
long-lived request from blocking store replacement.

Native owner remains `semantica/explorer/native_scope.py::NativeScope`; the
service is lifecycle orchestration only. The CLI process exits when the host
pipe closes. Regression evidence: `tests/explorer/test_native_service.py` plus
the full Explorer suite: 418 passed, 5 skipped.
