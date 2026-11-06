# Native community capacity and cancellation evidence

- Date: 2026-11-05
- Status: verified-in-stated-scope; full G4 capacity qualification remains open
- Inspected fork base: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe, dirty main
- Upstream reference: not inspected
- Related record: [community isolation](2026-11-05-community-validation-isolation.md)

## Reason and native assessment

The existing `semantic_artifact_builder._native_community_operation` delegates
GraphBuilder validation and exact CommunityDetector greedy modularity to
`ParallelismManager.execute_isolated_task`. That executor owns its only
production caller. It preserves bounded exact-JSON transport, sampled worker RSS,
deadline, cancellation and reaping. Existing tests cover generic operation
failures and publication rejection, but did not measure a successful native graph
operation including its parent's input construction, transport and result receipt.

Reuse those owners unchanged. No new algorithm, parser, resource configuration,
store, model, dependency, network call or public protocol is introduced.

## Actual change

`tests/test_native_community_capacity.py` adds:

- Full native GraphBuilder and exact greedy-modularity runs for 2,048 and 10,000
  connected clustered nodes, plus a 2,048-node single-hub graph.
- 10 ms parent/descendant RSS sampling beginning before topology construction and
  ending after complete result receipt. Child, parent and simultaneous combined
  peaks are recorded separately, along with elapsed time, nodes and edges.
- Exact complete membership and no repeated or missing node identities.
- Actual native-handler cancellation after an on-disk handler-entry marker,
  cancellation return within one second and no surviving operation child.

This is supporting capacity evidence, not a benchmark fixture that defines the
product's acceptance limits. Existing 120-second, 1-GiB worker and 16-MiB transport
ceilings remain unchanged. No pass criterion or baseline is changed.

## Verification

`.venv/bin/python -m pytest -q -s tests/test_native_community_capacity.py`
passed all 4 tests in 31.58 seconds. Log:
`/tmp/g4-community-capacity-tests.log`. Individual receipts are also written to
the pytest temporary directory as `capacity.json`.

`.venv/bin/python -m pytest -q tests/pipeline/test_isolated_task.py`
passed all 17 isolation regressions in 2.61 seconds. Log:
`/tmp/g4-community-capacity-isolation-regression.log`. `git diff --check` passed.

| Input | Time | Parent peak RSS | Worker peak RSS | Simultaneous combined peak |
| --- | ---: | ---: | ---: | ---: |
| 2,048 clustered / 7,423 edges | 1.67 s | 141,033,472 | 123,158,528 | 263,831,552 bytes |
| 10,000 clustered / 36,249 edges | 4.70 s | 154,025,984 | 171,573,248 | 247,775,232 bytes |
| 2,048 hub / 2,047 edges | 23.44 s | 79,331,328 | 117,800,960 | 187,318,272 bytes |

Fresh standalone-process probes independently observed clustered 10,000 nodes /
36,249 edges at 2.22 seconds, combined peak 301,350,912 bytes; hub 2,048 nodes /
2,047 edges at 23.24 seconds, combined peak 230,195,200 bytes. Differences between
runs include Python allocator history and concurrent work; these figures must not
be extrapolated as an arbitrary topology guarantee. Full membership completed
and no operation child survived in each probe.

## Limits and remaining decisions

A sparse hub is over five times slower than the larger clustered fixture. Node
and edge counts alone therefore do not establish an exact modularity capacity
contract. No approved current G4 target topology/size was found in the current
remediation plan; its older 300,000-entity / 1,000,000-relation UA migration budget
belongs to a different operation and must not be imported here.

The sampling is observational, not an OS memory ceiling. Parent RSS includes the
pytest process but excludes an entire real project's semantic DTOs, model output,
and consumers. Input JSON writing checks cancellation/deadline incrementally;
Popen startup and bounded (at most 16 MiB) parent `json.loads` result decoding
remain synchronous between checks. No unkillable decoding thread or duplicate
parser was added to conceal that limitation. Real ESG topology qualification,
full-builder resource qualification and immutable-artifact acceptance were not
run. This evidence does not close G4 or permit release.

## Upstream merge assessment

Pending upstream review. Preserve exact native algorithm delegation, complete
membership and real child cancellation. Re-run capacity measurements on a changed
GraphBuilder, CommunityDetector, NetworkX or executor; do not preserve numerical
machine measurements as algorithm-independent promises.
