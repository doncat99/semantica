import test from 'node:test';
import assert from 'node:assert/strict';
import { filterGraphInput } from '../src/workspaces/GraphWorkspace/graphFilters.ts';

const nodes = [
  { id: 'a', type: 'concept', content: 'Capital market' },
  { id: 'b', type: 'person', content: 'Analyst' },
  { id: 'c', type: 'concept', content: 'Risk' },
];
const edges = [
  { id: 'ab', source: 'a', target: 'b', type: 'studies' },
  { id: 'ac', source: 'a', target: 'c', type: 'affects' },
];

test('node and relationship filters intersect without dangling edges', () => {
  const result = filterGraphInput(nodes, edges, { nodeType: 'concept', edgeType: 'affects', text: '' });
  assert.deepEqual(result.nodes.map(n => n.id), ['a', 'c']);
  assert.deepEqual(result.edges.map(e => e.id), ['ac']);
  assert.deepEqual(nodes.map(n => n.id), ['a', 'b', 'c']);
});

test('text is literal case-insensitive content and no match remains empty', () => {
  assert.deepEqual(filterGraphInput(nodes, edges, { text: 'CAPITAL', nodeType: '', edgeType: '' }).nodes.map(n => n.id), ['a']);
  assert.deepEqual(filterGraphInput(nodes, edges, { text: '.*', nodeType: '', edgeType: '' }), { nodes: [], edges: [] });
});

test('relationship scope excludes unrelated isolates and clearing restores all input', () => {
  assert.deepEqual(filterGraphInput(nodes, edges, { text: '', nodeType: '', edgeType: 'studies' }).nodes.map(n => n.id), ['a', 'b']);
  assert.deepEqual(filterGraphInput(nodes, edges, { text: '', nodeType: '', edgeType: '' }), { nodes, edges });
});
