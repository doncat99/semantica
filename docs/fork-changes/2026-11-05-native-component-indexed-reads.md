# Native identity component point reads

- Record ID: 2026-11-05-native-component-indexed-reads
- Date / author: 2026-11-05 / Codex
- Status: verified-in-stated-scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty main, preserve prior cutover work)
- Upstream reference: not inspected; local native owner repair
- Related records: G4 native builder cutover

## Reason and scope

Actual full deterministic build profiling found a repeated project-wide join in
IdentityCandidateIndex._page and hydrate_component. Each component's SPARQL query
rejoined identityMember and identityOrdinal across the project, even when the
component contained one member. In the 4-source x 32-passage profile, these two
paths issued 1,026 queries. Native object-index reads already support the needed
exact component lookup. This change repairs that existing owner.

## Native capability assessment

- Existing owner: semantica/triplet_store/identity_candidate_index.py::IdentityCandidateIndex.
- Callers: semantic_artifact_builder.py entity_resolution and native canonical hydration.
- Tests: tests/triplet_store/test_identity_candidate_index.py.
- Decision: repair native storage access, retain existing connectivity and resolver semantics.
- No second index, cache, resolver, fallback or storage owner is introduced.

## Actual changes

Component queries now first bind identityComponent's object through the native
quad index. Membership remains a native point check, ordinals are projected for
only those component members, and a heap retains at most limit+1 page candidates.
The pre-hydration count uses the same iterator and stops at max_members+1 before
hydrating any DTO. Root traversal, generation fencing, cancellation, cursor scope,
all component members and existing budgets remain enforced. No stored-data or
external protocol migration, dependency, model, network or cost impact.

## Verification and limitations

- Red: new test_component_reads_only_its_native_reverse_index fails on old code,
  rejecting the global component SPARQL join (/tmp/g4-component-red.log).
- Green: all 11 identity index tests pass in 7.99s, covering complete cross-page
  membership, restart, foreign cursors, exact bytes and pre-hydration rejection
  (/tmp/g4-component-green.log).
- Same native 256-singleton store, all 256 lookups: old page query 0.2502s;
  current full component API including fences 0.1045s. This is a focused access
  comparison, not a full-build throughput claim.
- Full 4x32 profiling before: 24.04s; after: 83.54s. Environment contention affected
  unrelated reader/flush paths as well, so these elapsed times are not comparable.
  The after profile confirms component page/count query calls were removed:
  _page now executes only two queries for root traversal, hydrate_component none.
- Complete ESG capacity and packaged acceptance remain outside this focused fix.
- Large components require a complete native component traversal for exact page
  ordering, with limit+1 heap retention. The hydration record limit remains 4096.

## Upstream merge assessment

- Disposition: keep; repairs local native index access without changing semantics.
- Incoming upstream revision: not reviewed.
- Likely conflict: IdentityCandidateIndex component traversal.
- Retain only with restart, complete cross-page, budgets and stale-generation tests.
