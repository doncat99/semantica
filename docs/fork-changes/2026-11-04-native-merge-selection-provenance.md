# Native merge selection provenance

- Date: 2026-11-04
- Status: focused native-owner checks passed; G4 publication integration pending.
- Inspected owner: `MergeStrategyManager.merge_entities`, `EntityMerger.merge_entity_group`,
  `EntityResolver.resolve_entities`; current canonical checkout on `main`.

G4 reference-only identities require the actual native property selection, not a
second stored merged entity. The native merge result now records property source
IDs at the decision point. First/last selections retain the chosen source;
merge-all retains contributions; a custom computed value explicitly has no
source-only representation. It must not be persisted as an invented source ref.
The resolver exposes these selections alongside representative/member IDs for
the current call and clears them on the next call. Existing merged dictionaries
remain transient computational output until the G4 producer cutover.

Merge-all no longer mutates an input property's list. This protects original
source observations without copying their business fields to a second store.

New specs were red before the implementation. Native selection, deduplication,
identity constraints, resolution veto and exact resolver regression selection:
**122 passed / 3.13s**. No model calls or formal profile writes. This does not
prove aggregate publisher removal, bounded consumer integration or App acceptance.
Native source IDs remain required for durable references; custom computed
properties need explicit product treatment rather than guessed provenance.

Upstream merge assessment: the extension belongs to the existing merge/resolver
owners; no alternate resolver, persistence module, algorithm or dependency added.
# Verification correction (2026-11-04)

The later combined run including build lifecycle, exact merge provenance,
deduplication, identity constraints, native resolution veto and exact entity
resolution completed **128 passed / 1.37s**. The earlier result remains the
historical narrower run. This is focused evidence, not release acceptance.
