# Native greedy-modularity topology and resource audit

- Record ID: 2026-11-04-native-community-topology-resource-gap
- Date / author: 2026-11-04 / Codex
- Status: minimal private topology projection implemented; direct NetworkX
  conversion remains a test-only experiment; native resource gap remains open
- Fork base revision: 24ef316816ea0141a1f30b571ce8dcbbd2d78bfe
- Upstream assessment: pending
- Gate: G4 remains incomplete; not release or ESG acceptance evidence

## Actual owner path and retained state

`semantic_artifact_builder._semantic_organization` calls
`_canonical_graph_projection`. Before this change that helper constructed all entity dictionaries
(`id`, text/name, type, metadata) and relationship dictionaries (`id`, source,
target, type, expanded metadata/evidence IDs), then invokes native
`GraphBuilder(merge_entities=False, resolve_conflicts=False, fail_closed=True)`.
GraphBuilder shallow-copies every dictionary to normalize it, creates an
additional filtered entity reference list, validates known endpoint IDs, and
returns entity/relationship lists. The helper verifies exact identity sets and
returned relationships. These were containers and metadata references, not new
copies of plain body-string bytes. The currently supported fail-closed graph
validation must remain owned by GraphBuilder.

Organization constructs another entity-ID dictionary list and sends it with
the canonical relationships to `CommunityDetector` using explicit
`greedy_modularity`. `_to_networkx` first constructs `GraphView`: normalized
node/edge lists and node/ordered-edge deduplication sets. While those lists
remain live it copies their topology into an unweighted undirected
`networkx.Graph`. The dictionary path discards relation attributes and
collapses repeated and reversed endpoint pairs; explicit isolates and loops
remain. A supplied NetworkX graph is already returned without conversion.

`detect_communities_greedy_modularity` then runs NetworkX's greedy algorithm,
computes modularity, sorts complete groups, and returns communities plus all
node assignments. Organization consumes only communities and partitions the
original relations once using their IDs and endpoints. Removing the returned
node assignments would change a public CommunityDetector result contract;
they are not an unrestricted copy-removal target.

## Smallest seams and implementation boundary

1. **Implemented:** At the private graph-projection call, supply only entity IDs and relation
   IDs/endpoints needed for graph validation and subsequent organization.
   Retain GraphBuilder, its fail-closed endpoint checks, identity-set checks,
   candidate order and native ownership. Full organization output was
   characterized before removing unused names/types/metadata from this projection.
   Do not remove GraphBuilder's general-purpose normalization copies: they
   also protect callers from mutation and serve other consumers.
2. **Not implemented:** Within the existing native topology owner, factor normalized node/edge
   traversal so CommunityDetector can populate the single NetworkX graph
   directly. Preserve current normalization and exact insertion order,
   including valid implicit nodes from an edge whose counterpart normalizes
   to an invalid ID. NetworkX itself supplies deduplication for this simple
   unweighted graph. Other GraphView consumers can retain their materialized
   view. Do not implement a second topology normalizer or change algorithm,
   graph kind, weights, loops, isolates, tie order, resolution or return DTO.

The proposed second seam would remove conversion-time duplicate lists/sets. It would not
remove the final NetworkX topology or greedy algorithm's global work state.

## Actual offline allocation and equivalence evidence

### Implemented private projection: red specification and exact organization parity

`tests/test_native_organization_topology_projection.py` captures complete
serialized communities and topics for all 64 four-node simple graphs plus a
qualified-fact/report fixture containing loop, duplicate and reversed edges,
isolates, overview-grounded topics and metadata/support observations. The
pre-change full-output golden SHA256 is
`1f75e04dd349f60471b066c7802128c575d0598f46d925ada1f50536901493ef`.
It is unchanged after implementation. Complete original entity/assertion/
relation/evidence/report model dumps are unchanged, including qualified
metadata, support observations, relation order and all evidence IDs.

The boundary red spec observes the real GraphBuilder call and requires only
entity `id` and relation `id`/`source`/`target` fields. On the original code:
**1 failed, 4 passed in 0.91s**, solely on unused projected payload. Separate
specifications verify the real native fail-closed missing-endpoint error and
exact identity checks when either entity or relation candidates disappear.
GraphBuilder, its general normalization copies and every public DTO remain
unchanged; no resource threshold, algorithm or admission policy was added.

After implementation, focused organization/community/reading-report command:

```text
.venv/bin/python -m pytest -q tests/test_native_organization_topology_projection.py tests/kg/test_native_community_topology_audit.py tests/kg/test_community_detector_dispatch.py tests/kg/test_graph_view_input_residency.py tests/test_reading_report_admission.py tests/test_kernel_owner_regressions.py::test_organization_does_not_reinterpret_admitted_identity tests/test_kernel_owner_regressions.py::test_organization_partitions_facts_without_rescanning_per_community tests/test_kernel_owner_regressions.py::test_native_community_algorithm_and_isolates_are_explicit -k 'not snapshot_bytes_do_not_depend_on_build_directory'
```

Result: **63 passed, 1 deselected in 3.32s**. The one excluded historical
reading-report test still injects deleted `resumeCheckpointDirs`; a preceding
broader run showed its explicit schema failure (**1 failed, 93 passed,
1 deselected in 4.82s**). That fixture migration remains separate integration
work, not a passing acceptance result.

### Unimplemented direct NetworkX conversion experiment

Added test-only experiment
`tests/kg/test_native_community_topology_audit.py`; it uses existing native
normalization helpers and installed NetworkX 3.6.1, without models, new
dependencies or production data. All 64 four-node simple graphs preserve
ordered nodes/edges and the entire greedy result, including modularity and
assignments. Additional coverage includes duplicate/reversed edges, loops,
isolates, implicit nodes, malformed records, normalized invalid endpoints and
NetworkX pass-through identity. These are finite characterization cases, not
a proof over every accepted custom graph object.

`tracemalloc` starts after constructing input; both resulting graphs remain
intact and equal. Actual test-run conversion allocation:

| Nodes / edges | Current peak bytes | Direct experiment peak bytes |
| --- | ---: | ---: |
| 4,097 / 4,096 | 1,894,544 | 1,487,812 |
| 16,385 / 16,384 | 7,246,288 | 5,944,260 |

These values are Python allocation observations on path graphs, not RSS,
admission budgets, worst-case guarantees, release limits or total build
memory. The tests report measurements and enforce equivalence, without
introducing a production budget constant or fragile peak threshold.

Separate direct native greedy calls on prebuilt path graphs measured:

| Nodes / edges | Greedy peak Python bytes | Elapsed seconds |
| --- | ---: | ---: |
| 256 / 255 | 364,955 | 0.041 |
| 1,024 / 1,023 | 1,437,992 | 0.222 |

This separately demonstrates retained algorithm work even after conversion
copies are removed; it does not extrapolate to dense or adversarial graphs.

Focused command: `.venv/bin/python -m pytest -q
tests/kg/test_native_community_topology_audit.py
tests/kg/test_community_detector_dispatch.py
tests/kg/test_graph_view_input_residency.py
tests/test_kernel_owner_regressions.py -k 'not query and not retrieval_index'`:
**74 passed, 7 deselected in 2.36s**.

The initial unfiltered combined run was **6 failed, 75 passed in 2.55s**.
All six failures are pre-existing query/snapshot fixtures importing removed
`test_semantic_query_worker` helpers or `semantic_query._load_json`; no change
to those fixtures or query production was made in this investigation. They
remain integration work, not passes.

## Native capability gap requiring a resource-contract decision

Installed NetworkX greedy modularity holds the complete graph, degree maps,
bidirectional modularity-gain dictionaries, per-row mapped heaps, a global
best-merge heap and evolving community frozensets. These encode the current
global greedy objective and tie behavior; they cannot simply be discarded or
replaced by independently processing chunks. The public call has no progress,
cancellation, spill-to-disk, restart/checkpoint or enforced total memory/time
contract. Conversion copy removal does not add those capabilities.

Concrete native-owner options for discussion are:

- Keep exact current NetworkX greedy semantics in an owned operation process,
  with progress/cancellation and an explicitly agreed resource envelope and
  typed failure behavior. Process isolation permits termination but does not
  reduce intrinsic memory or establish completion for arbitrary graph size.
  Define the input-size/density evidence and operational service objective
  before choosing any limit; no limit or silent truncation is proposed here.
- If the required scope cannot complete within that envelope, implement and
  characterize an exact native external-memory greedy execution plan preserving
  global modularity gain and tie ordering. This is substantial new native
  capability, not a harmless copy deletion or an existing supported feature.
  Persist operation/evidence identities and define recovery before promising
  restart behavior. Do not retain obsolete snapshot payloads as execution state.

Changing algorithm, chunking independent partitions, dropping edges or
reducing recall would change semantic output and requires a separate product
decision. None is implemented or implied by this record.

## 2026-11-04 subsequent implementation correction

The earlier test-only direct conversion is now implemented in the native
CommunityDetector using existing normalization helpers. The old construction
is retained solely as a test oracle. Exact native greedy execution also now
uses ParallelismManager's isolated task boundary. See
[the operation record](2026-11-04-native-community-operation-isolation.md)
for red/green evidence, complete golden, cancellation/parent-death behavior
and explicit synchronous-transport/sampled-RSS limits. Earlier proposed-only
statements describe their historical point. Global resource qualification and
G4 remain incomplete; process containment does not prove a bounded build.
