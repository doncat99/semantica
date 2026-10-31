# Explorer graph scope and initial overview

- Date: 2026-10-31
- Status: implemented and native Explorer verified; consumer delivery pending
- Fork base revision: 4238420f621da715a69426b937d0ab4a0b312c20
- Upstream reference: not independently refreshed

## Native capability assessment

GraphWorkspace owns the full/grouped/focused modes; graphSceneState owns native
community aggregation and local exploration. useLoadGraph owns pagination and
the graph store. SearchCommandBar only locates nodes; it does not filter the
display. The graph REST owner supports individual type filtering but the full
loader does not expose it. Repair this native loading owner with cached input
and explicit node/relationship/text scopes, retaining native layouts. No host
graph implementation or alternate community algorithm is introduced.

## Approach and consumer impact

Cache the paginated immutable session input, scope before populating the store,
and expose data-derived filter choices and matched counts in GraphWorkspace.
Relationship scope retains only admitted endpoints. Empty matches stay empty.
Use the existing grouped overview on initial load where available. Filters
reset selection and path; no persisted graph or host artifact is modified.

## Verification and limitations

Native Explorer build passed. Workspace regressions: 165 passed; graph store:
1 passed. Chrome browser regressions: graph scopes and existing legend both passed.
Scopes cover intersections, literal text, empty results, repeated clear, cached
input, explicit reload, read-only requests and a 900px toolbar overflow check.
Screenshots were inspected locally. Publication, consumer pin and packaged
runtime verification remain pending. No claim of packaged delivery yet.

## Upstream merge assessment

Pending; retain only while upstream lacks these native controls. Reconcile the
loader and workspace owners directly if upstream introduces equivalent scope.
