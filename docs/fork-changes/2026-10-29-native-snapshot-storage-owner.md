# Native snapshot storage ownership

- Date: 2026-10-29
- Inspected revision: 02ac4e44d; local upstream reference 0a2731c8223426efaa0dd9e9b345a8411ff3d4f0
- Status: implemented; native composition and affected regressions verified
- Native owners: GraphStore.append_snapshot, EntityMerger.merge_qualified_facts,
  ConflictDetector.qualified_polarity_groups/qualified_value_groups,
  TemporalVersionManager.compare_collections.

GraphStore currently imports the source artifact builder to compose stored
observations. The builder contains typed-contract mapping for native fact merge,
conflict detection and change comparison. Reuse these algorithms; transfer their
typed entry points to ConflictDetector and TemporalVersionManager. Native graph
storage owns observation composition; builders consume those owners. Retain
single-hop imports of existing builder exports for callers, without wrappers,
alternate algorithms or new storage.

Preserve immutable evidence/observation IDs, withdrawal/replay, scope and contract
validation, native conflict semantics and bounded atomic-head CAS retries. Never
weaken accepted results or publish unrelated contextual-identity/report drafts.
Regression: reject builder imports while appending and exercising CAS retry;
existing append/fact/context/build tests remain relevant. No real data mutation.
Case capability-library-prepare / journey-library, delta keep; no gates/baselines
changed. Actual external Neo4j integration requires an isolated configured URI.
Upstream assessment pending runtime evidence; retain one native owner on merges.

Evidence: import-blocking append/CAS spec failed against the old storage owner;
after consolidation, conflicts/change-management/append/fact/context/query/build/
recovery selection: 219 passed, 31 subtests passed. Scope, immutable records,
withdrawal and original observation replay regressions pass. Existing external
Neo4j integration not run (no isolated URI selected). This change removes the
reverse builder dependency, not the native algorithms or required typed mapping.
Builder legacy exports are direct symbol aliases, not forwarding implementations.
Concurrent contextual-processing mismatch validation is preserved unstaged in
the new storage owner and excluded from this commit, like other unrelated drafts.
No artifact pin, App deployment or real ESG acceptance in this focused check.
