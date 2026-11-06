# Native identity cursor preparation

## Reason and owner assessment

Inspected `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` with prior
uncommitted G4 changes preserved. `EntityDisambiguator.prepare` owns grounded
project/source/scope definitions and contextual identity facts. It currently
iterates input repeatedly and caches supported facts by Python object address;
this does not accept native row cursors and cannot safely consume rehydrated
objects. `DuplicateDetector` owns candidate retrieval, conflict partition and
review summaries. `EntityResolver.resolve_entities` is the only canonical merge
path, used by the builder's `_resolve_native_entities` and native callers.

## Implemented change

Global preparation now accepts a callable returning a fresh row cursor for each pass; it also continues to accept reiterable rows. This allows global preparation from a repeatable row factory and keep supported-fact
lookup derived from the prepared semantic indexes instead of object addresses.
The existing resolver/detector can process one complete indexed candidate
component with already prepared project context. Preserve default unordered
list semantics, exact merge/partition behavior and complete review evidence.

## Validation and limits

Red specification: two failures before the change, recorded in `/tmp/g4-identity-cursor-red.log`. Focused contextual oracle run: 140 passed. Final owner suites (`tests/kg tests/deduplication tests/normalize`): 1193 passed, 45 skipped, 5 subtests passed in 9.87 seconds, with existing deprecation/numpy warnings; `/tmp/g4-identity-cursor-final.log`. Cursor tests verify hydrated rows are released, remote definitions remain visible across components, empty components retain context, and missing prepared context rejects explicitly. Scoped `git diff --check` passes. Candidate component
storage and persistence of contextual lookup indexes are separate parent-owned
integration seams; this change alone is not a bounded project build or G4 pass.
No model, network, release pin or artifact qualification is involved. No upstream merge or artifact update is claimed by this owner change.
