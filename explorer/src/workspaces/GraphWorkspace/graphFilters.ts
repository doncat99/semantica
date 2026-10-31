export type GraphFilters = { nodeType: string; edgeType: string; text: string };
export const EMPTY_GRAPH_FILTERS: GraphFilters = { nodeType: '', edgeType: '', text: '' };

/** Scope the native input before layout/aggregation; never mutate the session snapshot. */
export function filterGraphInput<N extends { id: string; type: string; content: string }, E extends { source: string; target: string; type: string }>(
  allNodes: N[], allEdges: E[], filters: GraphFilters,
): { nodes: N[]; edges: E[] } {
  const text = filters.text.trim().toLocaleLowerCase();
  let nodes = allNodes.filter(node => (!filters.nodeType || node.type === filters.nodeType)
    && (!text || node.content.toLocaleLowerCase().includes(text)));
  const ids = new Set(nodes.map(node => node.id));
  const edges = allEdges.filter(edge => ids.has(edge.source) && ids.has(edge.target)
    && (!filters.edgeType || edge.type === filters.edgeType));
  if (filters.edgeType) {
    const endpoints = new Set(edges.flatMap(edge => [edge.source, edge.target]));
    nodes = nodes.filter(node => endpoints.has(node.id));
  }
  return { nodes, edges };
}
