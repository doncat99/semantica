# Bounded native identity resolution scope and cooperative cancellation

- Record ID: 2026-11-06-native-identity-resolution-scope
- Date / author: 2026-11-06 / repository agent
- Status: implemented; verified only in the stated focused scope
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe, with existing local changes preserved
- Upstream reference: no new incoming upstream revision inspected
- Related records: native identity candidate/index and generation context records

## Reason and scope

The installed `sha256:aaa8527799adf4bf3a6c72815b3c2c0881ffcfea14f3fe1dfc3de95c8d190c9a`
artifact ignored a cancellation requested before a 16-member identity resolution.
A real native 64-member dense resolution performed 6,048 comparisons and 266,368
context lookups. Its cProfile time was 48.924 seconds; 42.848 seconds were spent
in complete publication input-plan fences, including 532,736 SPARQL queries.
The isolated installed 4,096-member probe was interrupted after 272.802 seconds,
without resolving the component. This is failure evidence, not capacity success.

## Native capability assessment

The existing owners are `EntityResolver`, `DuplicateDetector`,
`EntityDisambiguator`, `NativeIdentityContext`, and the shared
`check_query_cancellation`. Inspected callers include publication builder native
component resolution, graph builder, KG methods, resolver merge entry points,
and `EntityMerger.merge_entity_group`. Duplicate group pair scores are publicly
exposed in merger provenance; their existing semantics and representation remain.
No second resolver, persisted context, alternate identity algorithm, model, or
network call is introduced.

## Approach and actual changes

- The resolver wraps its existing computation in one component scope. Cancellation
  is checked before and after resolution, at every pair comparison, preparation
  row, and long partition iteration. Cancelled computations raise ProcessingError.
- Full immutable source/operation-plan validation occurs at native scope admission
  and successful result handoff. During the computation, generation and pending
  state are checked by keyed native reads at least every 128 context lookups or
  50ms. Cancellation is checked on every lookup. Stale output cannot be returned
  successfully; a regression changes generation after merge and checks rejection.
- Repeated entity features are memoized only after context preparation, within
  this immutable component, with a 16 MiB charged allocation limit. Feature entries
  contain derived scalars/sets rather than entity DTOs. They are cleared on exit,
  including failure, and never reused across runs or mutated input lists.
- Native context observations have a scope-local 128-key / 1 MiB bounded cache.
  Oversize valid observations are read fully without caching. Writes invalidate
  the cache; the final complete plan fence remains mandatory.
- Exact ordered pair decisions may be reused by the existing three consumers in
  the same scope. A byte per unordered pair holds separate direction codes,
  capped at 8 MiB; at most 15 templates share a 1 MiB charged allocation budget.
  An uncacheable decision is recomputed by the same authoritative operation.
  No candidates, constraints, provenance scores, or support evidence are dropped.
- Public signatures, processing results, extraction recipes and stored schemas
  are unchanged. No migration or deletion of user data is needed.

## Verification and limitations

Red evidence: `.tmp/g4-identity-cancellation-red.log` in the OntoScience workspace,
three cancellation specifications failed before the owner changes.
Focused tests include cancellation, complete pair reuse, ordered semantics,
cross-run invalidation, stale-generation handoff, complete small-graph oracle,
partition golden results, identity context and candidate indexes.
Actual current focused result and capacity receipts are recorded in the dated
follow-up below. Installed aaa852 remains immutable and does not include these
changes; its qualification cannot cover the changed source. The final candidate
must be rebuilt and qualified by the integration owner.

A prior source profile (before pair-result reuse) reduced the same native
64-member complete resolver workload to 0.853 seconds, with all 6,048 comparison
consumer calls preserved. This is a focused performance result, not real ESG
acceptance. Configured 4,096-member complete success, final candidate capacity,
and real ESG publication remain required. No arbitrary new public timeout/RSS
option was added; measured resource data must support the execution contract.

## Upstream merge assessment

Disposition: pending for the next incoming upstream revision. Inspect native
resolution cancellation, immutable context ownership, bounded memoization, pair
ordering, and generation fences. Adapt or remove this change if upstream supplies
these guarantees. Re-run complete candidate/partition oracles, stale-generation
handoff, cancellation, and measured maximum-component capacity after a merge.

## Dated follow-ups

- 2026-11-06: 169 focused tests initially passed before adding additional
  pair-reuse and handoff assertions. A newly added pair-count assertion initially
  exposed differing lexical versus numeric ID order; the memo now retains
  decisions separately for both ordered directions. No symmetry is assumed.

- 2026-11-06: frozen source focused qualification: **172 passed in 10.22s**,
  receipt `.tmp/g4-identity-focused-green.log` in the OntoScience workspace.
  The maximum-component probe invokes production `_resolve_native_entities`,
  validating complete support aggregation and all remap/registry members.
  Earlier interrupted source probes are diagnostic only, not passing capacity.
