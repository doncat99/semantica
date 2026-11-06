# Native qualified-fact group cursor

## Reason and owner assessment

Inspected dirty canonical fork `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe`.
`ConflictDetector.reconcile_qualified_facts` owns qualified identity and conflict
semantics; `EntityMerger.merge_qualified_facts` owns canonical representative,
independent support copying, exact JSON deduplication/order and status reduction.
The builder is the sole production consumer through its conflict-owner alias.
The existing merger groups every dumped project fact before its first yield.
A native indexed caller therefore needs the same owner to reduce one cursor group,
rather than reimplementing support semantics in storage or the builder.

## Implemented

- Expose `ConflictDetector.qualified_fact_identity(project_id, item, prefix)` and
  use it from current reconciliation. Its digest inputs and output remain exact;
  unknown fact kinds explicitly fail.
- Extract `EntityMerger.merge_qualified_fact_group(identifier, members)` as the
  single canonical reduction implementation. The generic unordered iterable API
  groups its input and delegates to this owner; indexed callers can supply one
  native identity group directly.
- Reduce each cursor row immediately. Keep only independently cloned unique
  audit observations, current representative and their ordering keys, rather
  than retaining the original member list. Preserve full support bodies,
  withdrawn observations, exact JSON ordering and derived statuses.

No storage, compatibility reader, alternative algorithm, model call, configuration,
export or dependency change is introduced. Builder/store integration is owned by
the parent G4 change; these primitives alone do not close the global resource gate.

## Evidence

New regression `test_qualified_fact_group_consumes_native_cursor_without_retaining_members`
uses 64 weak-referenceable native rows and checks release while consuming the
cursor; all complete support observations and evidence IDs remain available.
Red: 1 failed, 7 passed (`/tmp/g4-fact-native-cursor-red.log`).
Focused: 16 passed (`/tmp/g4-fact-native-cursor-green.log`).
Affected conflict/deduplication/status/support suites: 226 passed, 31 subtests
passed in 1.74s (`/tmp/g4-fact-native-cursor-final.log`).

## Limits and upstream assessment

The generic unordered-input API still groups all input records. Project-wide
conflict detection still builds canonical lists and indexes. A single canonical
fact still contains every required support, so its output and JSON ordering keys
scale with that support group; this patch does not silently truncate it or invent
a resource budget. Native ordered-group/sink integration and end-to-end scale
qualification remain required. No artifact, release pin or paid ESG qualification
was run. Upstream merging must preserve both unordered-input semantics and native
cursor row release; upstream assessment is pending.
