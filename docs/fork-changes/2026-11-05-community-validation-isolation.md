# Include canonical graph validation in the monitored community operation

## Native assessment and reason

Inspected canonical dirty fork main at 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe.
The native owners are semantic_artifact_builder._canonical_graph_projection,
GraphBuilder.build, CommunityDetector.detect_communities_greedy_modularity,
and ParallelismManager.execute_isolated_task. The only production caller of the
projection is the semantic organization stage. Previously the parent constructed
and normalized the entire GraphBuilder topology before starting the monitored
community operation. Child resource monitoring therefore missed those allocations
and that work; the parent also retained normalized edges throughout organization.

## Implemented change and affected callers

Move the existing canonical GraphBuilder validation and exact candidate identity
checks into _native_community_operation, before the unchanged greedy modularity
algorithm. Send only candidate IDs and endpoints through the existing JSON
transport. Both native owners now execute inside the same existing 120-second,
1-GiB sampled RSS envelope and 16-MiB transport ceiling, with cancellation and
child cleanup unchanged. These are existing ceilings, not increased budgets.

The parent partitions its original validated relation objects directly into the
returned communities; it no longer retains normalized graph edges, a relation-ID
lookup or duplicate expected-ID sets. Community titles read only their first
three names. Relation order, direction, parallel relations, self-loops, isolated
nodes, fact fields, evidence and topic semantics are unchanged. The helper now
accepts the same minimal topology dictionary passed to the child. Its direct
test callers were updated; the kernel regression now counts actual relation
iterations rather than a mocked projection which no longer runs in the parent.
No public schema, storage, pin, migration, dependency or algorithm changes.

## Red specification and verification

New test_graph_validation_runs_inside_the_monitored_operation fails on the
previous parent-side GraphBuilder call and passes after moving that call. It
also checks the exact minimal task input and unchanged complete node coverage.
Existing characterization covers all 64 four-node simple graphs, parallel and
reverse relations, self-loops, isolated nodes, topics, original input immutability,
unknown endpoints and exact candidate identity checks. Failure tests verify
community failure does not activate a publication.

Red log: /tmp/g4-community-validation-red.log (1 failed).
Initial organization/kernel/topology regression: 51 passed in 54.22s,
/tmp/g4-community-validation-green.log. Isolation owner regression: 17 passed in
2.77s, /tmp/g4-community-isolation-regression.log. Final merged verification is
recorded in the host remediation plan after execution.

## Limits and upstream disposition

This closes the unmonitored GraphBuilder working set, not total parent RSS.
The parent still owns the original project models and constructs one minimal
input topology; child RSS sampling every 50 ms is not an OS hard memory ceiling.
Global identity/fact working sets and topology input construction remain G4
qualification gaps. No arbitrary-scale exact algorithm support, real ESG product
acceptance or release qualification is claimed. Upstream merge assessment is
pending; preserve monitored-boundary and characterization tests when merging.
