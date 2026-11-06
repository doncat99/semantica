# Exact greedy modularity queue maintenance

- Record ID: 2026-11-05-community-queue-maintenance
- Date / author: 2026-11-05 / Codex
- Status: planned
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe (dirty main)
- Upstream reference: installed NetworkX 3.6.1 source; remote upstream not inspected
- Related records: 2026-11-05-community-validation-isolation

## Reason and scope

A 128-node hub incurs 64,388 MappedQueue push/remove operations. The existing
exact CNM scheduler repeatedly reconstructs the high-degree survivor row.
Repair scheduling overhead, preserving the exact algorithm, logical survivor,
floating arithmetic, tie order and all input edges. This is not ESG capacity acceptance.

## Native capability assessment

- Owner: CommunityDetector.detect_communities_greedy_modularity, dispatch at
  community_detector.py; builder _native_community_operation and isolated organization.
- Inspected installed NetworkX _greedy_modularity_communities_generator and
  MappedQueue; existing detector dispatch, topology audit, organization tests.
- Repair native owner: replace its direct NetworkX CNM scheduling call with one
  private exact scheduler using existing NetworkX Graph/MappedQueue/modularity.
  No fallback or selectable second algorithm. NetworkX remains test oracle.

## Approach and actual changes

- Planned private scheduler bulk-heapifies the survivor row, discards deleted
  row directly, and maintains one row maximum per live row. Preserve directed,
  multigraph, loops, resolution and size-sorted final community order.
- Detector delegates to that scheduler in place. No worker/DTO/storage change.
- New queue regression and exhaustive/seeded exact oracle tests.
- No model/network calls, new dependencies, persisted-data migration or pins.

## Verification and limitations

- RED: tests/kg/test_greedy_modularity_queue.py -k hub: 1 failed, operations
  64,388 > 1,024; /tmp/g4-community-queue-red.log.
- Green, caller checks and capacity measurements pending implementation.
- Still graph-sized storage and potentially quadratic score updates; no
  topology-independent time bound or real ESG qualification claimed.

## Upstream merge assessment

- Disposition: pending; incoming upstream revision not yet reviewed.
- Likely overlap: community_detector and NetworkX CNM scheduler.
- Retain only while exact oracle/queue regression passes; prefer an equivalent
  upstream repair when available. Recheck native organization and cancellation
  consumers and rebuilt immutable artifact after merge.

## 2026-11-05 implementation and verification

Status: verified-in-stated-scope. Implemented private `_greedy_modularity.py`,
replacing detector's direct upstream scheduling call. Embedded upstream BSD
notice in module so wheel includes it. No selectable alternate path retained.

- `/tmp/g4-community-queue-green.log`: initial 18 tests passed, including all
  1023 nonempty five-node simple graphs and directed/multigraph seeded cases.
- `/tmp/g4-community-queue-integration.log`: 111 passed / 97.71s, covering exact
  per-merge gains/partitions across hub/double-star/broom/bipartite/bridge/tree,
  resolution/tie-ID variations, topology projection, existing kernel callers,
  isolated capacity, fail-fast, timeout and cancellation.
- Full isolated 2048-node hub: 12.9768s, combined sampled RSS 229,490,688 bytes,
  versus prior 23.2354s / 230,195,200 bytes. Concurrent integration was running;
  these observations are measurements, not a deterministic speed guarantee.
- 10,000-node / 36,249-edge clustered graph: 3.4429s / 296,419,328 combined
  sampled RSS bytes. Both probes include parent/recursive child sampling every
  10ms and end without child processes. `/tmp/g4-community-queue-hub.json`,
  `/tmp/g4-community-queue-10000.json`.
- Real ESG capacity, final rebuilt dev artifact, host lifecycle and release
  acceptance remain separate unresolved gates. No paid model call or publish.
