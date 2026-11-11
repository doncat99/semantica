import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
Object.assign(globalThis, { React, window: dom.window, document: dom.window.document,
  HTMLElement: dom.window.HTMLElement, Node: dom.window.Node });
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: dom.window.navigator });
const { render, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
const { NativeScopeControls } = await import('../src/NativeScopeControls.tsx');

test('opens completed themes without treating topology communities as themes', async () => {
  const original = globalThis.fetch;
  const requests: Array<{ url: string; body?: string }> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    requests.push({ url, body: init?.body as string | undefined });
    const value = url === '/api/native-scope' ? { available: true, active: { selection: {}, nodeCount: 2, linkCount: 1, next_cursor: null, link_next_cursor: null } }
      : url.includes('catalog') ? { nodes: [{ id: 'topic:one', title: 'Climate' }], next_cursor: null }
      : { selection: { topicId: 'topic:one' }, nodeCount: 2, linkCount: 1, next_cursor: null };
    return new Response(JSON.stringify(value), { status: 200 });
  };
  try {
    let changes = 0;
    let ready = 0;
    const view = render(<QueryClientProvider client={new QueryClient()}>
      <NativeScopeControls onReady={() => { ready++; }} onChange={() => { changes++; }} />
    </QueryClientProvider>);
    await waitFor(() => assert.ok(view.getByLabelText('Scope kind')));
    assert.equal((view.getByLabelText('Select native scope') as HTMLSelectElement).value, '');
    assert.ok(view.getByRole('status').textContent?.includes('2 nodes'));
    assert.equal(requests.filter(r => r.url.endsWith('/select')).length, 0);
    assert.equal(ready, 1);
    assert.ok(view.getByRole('option', { name: 'Topology communities' }));
    fireEvent.change(view.getByLabelText('Scope kind'), { target: { value: 'topics' } });
    await waitFor(() => assert.equal((view.getByLabelText('Scope kind') as HTMLSelectElement).value, 'topics'));
    assert.ok(requests.some(r => r.url.endsWith('kind=topics')));
    fireEvent.change(view.getByLabelText('Select native scope'), { target: { value: 'topic:one' } });
    fireEvent.click(view.getByRole('button', { name: 'Open scope', exact: true }));
    await waitFor(() => assert.equal(changes, 1));
    assert.equal(requests.find(r => r.url.endsWith('/select'))?.body, JSON.stringify({ topicId: 'topic:one' }));
    assert.ok(view.getByText(/2 nodes, 1 links/));
  } finally { cleanup(); globalThis.fetch = original; }
});

test('shows complete graph totals without graph pagination and preserves the graph on filter failure', async () => {
  const original = globalThis.fetch;
  const selections: Array<Record<string, string>> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    let value: unknown;
    if (url === '/api/native-scope') value = { available: true, active: { selection: {}, nodeCount: 130, linkCount: 260 } };
    else if (url.includes('catalog')) value = { nodes: [{ id: 'source', title: 'Report' }], next_cursor: null };
    else {
      const selection = JSON.parse(String(init?.body));
      selections.push(selection);
      if (selection.sourceId) return new Response(JSON.stringify({ detail: 'Publication changed' }), { status: 422 });
      value = { selection, nodeCount: 130, linkCount: 260 };
    }
    return new Response(JSON.stringify(value), { status: 200 });
  };
  try {
    const view = render(<QueryClientProvider client={new QueryClient()}>
      <NativeScopeControls onChange={() => {}} />
    </QueryClientProvider>);
    await waitFor(() => assert.ok(view.getByRole('status').textContent?.includes('130 nodes, 260 links')));
    assert.equal(view.queryAllByRole('button', { name: /(?:Next|Previous) (?:node|link) page/ }).length, 0);
    assert.equal(selections.length, 0);
    fireEvent.change(view.getByLabelText('Select native scope'), { target: { value: 'source' } });
    fireEvent.click(view.getByRole('button', { name: 'Open scope', exact: true }));
    await waitFor(() => assert.equal(view.getByRole('alert').textContent, 'Publication changed'));
    assert.ok(view.getByRole('status').textContent?.includes('130 nodes, 260 links'));
    fireEvent.click(view.getByRole('button', { name: 'Project graph', exact: true }));
    await waitFor(() => assert.equal(selections.length, 2));
    assert.deepEqual(selections.at(-1), {});
  } finally { cleanup(); globalThis.fetch = original; }
});
