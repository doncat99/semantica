# Stream raw graph dictionary references

## Reason and inspected owner

Inspected `main` at `24ef316816ea0141a1f30b571ce8dcbbd2d78bfe` with existing
uncommitted remediation changes. Native `semantica/kg/_graph_view.py`
`_extract_nodes` and `_extract_edges` concatenate dictionary collections into
temporary project-sized reference lists before normalization. Their callers
iterate these values in `build_graph_view`, `build_edge_type_index`, and
`graph_node_ids`; no caller requires a raw list. Community, centrality and
hierarchy consumers remain owned by these native modules.

## Approach and scope

Implemented: traverse the existing dictionary collections with standard-library
iterators, preserving collection order, node-key projection, identity and all
records. Keep object-shaped graph behavior and downstream normalization intact.
No algorithm replacement, new store, changed graph membership, or truncation.

## Regression evidence

Before source fix, `tests/kg/test_graph_view_input_residency.py`: 2 failed,
1 passed. Traversing 16,384 native records allocated 131,416 bytes for nodes
and 131,248 bytes for edges; the specification allows less than 16,384 bytes
of traversal overhead, checks every original record identity and the complete
tail, and separately checks normalized order, duplicate edges and isolation.

After the source fix, the residency specification and affected detector dispatch,
centrality, label propagation, hierarchy and summarizer regressions: **201 passed**.
Dictionary inputs use `itertools.chain.from_iterable`; object inputs and native
normalization remain unchanged. Scoped whitespace checks passed.

## Limits and upstream assessment

This removes only the raw dictionary-input reference copies. Normalized graph
lists, NetworkX topology and greedy modularity working state remain resident;
there is still no complete graph node/edge/byte/work/deadline/cancellation
budget. It does not close G4. No models, network, packaging or profile writes.
Upstream assessment: pending comparison with an actual incoming revision;
reuse an equivalent upstream iterator implementation if provided.
