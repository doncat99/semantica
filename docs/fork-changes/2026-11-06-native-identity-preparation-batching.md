# Bound native identity preparation overhead

- Record ID: 2026-11-06-native-identity-preparation-batching
- Date / author: 2026-11-06 / Codex
- Status: implemented; focused source qualification passed, runtime qualification pending
- Fork base revision: 8e94edd81a1951b977600d913d46cabfd86efd2f
- Upstream reference: not inspected

## Reason and native assessment

Real ESG entity resolution remains active after 24 minutes. An isolated 200-entity
profile reproduced 4,207 complete input-plan checks and 207 flushes in 2.687s;
preparation consumed 2.233s. Native owners are IdentityCandidateIndex.build,
NativeIdentityContext.resolution_scope, and PublicationRecords.checkpointed.
Preparation is the sole production caller supplying NativeIdentityContext to
EntityDisambiguator.prepare; component resolution already uses resolution_scope.
Repair this handoff by reusing these existing scope and bounded durability owners.

## Approach and impact

Use generation-checked preparation boundaries and existing 128-write/256KiB
flush batches. Preserve every semantic observation, per-key resource validation,
cancellation and pending-generation mutation checks. No model, recipe, schema,
storage carrier or consumer contract change. No active runtime mutation.

## Verification and limitations

The preparation scope now reuses complete input-plan validation at handoffs,
with generation/state checks during operations and existing bounded write batches.
The canonical component loop also holds the input-plan scope: its keyed native
reads previously repeated the complete project plan for every entity.

34 focused identity, cursor, canonical-entity and pipeline tests passed in 21.18s.
An isolated 200-entity disk-backed comparison retained 200 members in both runs:
preparation 3.808s to 0.501s, total index construction 4.360s to 0.973s. The old
behavior was measured by disabling the new plan/resolution/write scopes in the
same native owner; this is a local comparison, not real ESG throughput evidence.
Additional cancellation and generation-change specifications exercise preparation
as well as staging; final results will be appended after execution.
Real build and final immutable artifact evidence remain outstanding.

Final focused check: 24 identity candidate, build cursor and canonical entity
specifications passed in 5.66s. The generation-change fixture now mutates once
across the resolver's repeated traversals, so it tests stale-generation rejection
rather than issuing a second conflicting mutation itself. Cancellation followed
by reopen/retry, scope cleanup and complete membership remain covered.

## Upstream merge assessment

Pending; retain only while native preparation lacks these existing scopes.
Re-run identity and build cursor regressions after any overlapping merge.
