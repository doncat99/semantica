import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';
import test from 'node:test';
import { chromium, type Page } from 'playwright';

const base = 'http://127.0.0.1:4176';
const nodes = Array.from({ length: 80 }, (_, i) => ({
  id: `n${i}`, type: i % 2 ? 'Person' : 'Concept', content: `Topic ${i}`,
  properties: { community: `group${Math.floor(i / 20)}` },
}));
const edges = nodes.map((node, i) => ({
  id: `e${i}`, familyId: `e${i}`, source: node.id,
  target: `n${Math.floor(i / 20) * 20 + (i + 2) % 20}`,
  type: i % 2 ? 'STUDIES' : 'RELATES', weight: 1, properties: {},
}));

async function graphSize(page: Page, order: number, size: number) {
  await page.waitForFunction(async ([expectedOrder, expectedSize]) => {
    const path = '/src/store/graphStore.ts';
    const { graph } = await import(path);
    return graph.order === expectedOrder && graph.size === expectedSize;
  }, [order, size]);
  await page.getByRole('group', { name: 'Graph filters' }).getByRole('status')
    .filter({ hasText: `${order} / 80 nodes` }).waitFor();
}

test('large graph overview, intersecting scopes, empty results, repeated clear and reload', async t => {
  const server = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '4176', '--strictPort'], { stdio: 'ignore' });
  t.after(() => { server.kill(); });
  let ready = false;
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(base)).ok) { ready = true; break; } } catch { /* Starting Vite. */ }
    await delay(100);
  }
  assert.ok(ready);
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  let nodeRequests = 0;
  const writes: string[] = [];
  await page.routeWebSocket('**/ws/graph-updates', () => {});
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (!['GET', 'HEAD'].includes(route.request().method()) && path !== '/api/graph/search') writes.push(path);
    let json: unknown = {};
    if (path === '/api/info') json = { capabilities: { agent_memory: false } };
    if (path === '/api/graph/stats') json = { node_count: nodes.length, edge_count: edges.length };
    if (path === '/api/graph/nodes') { nodeRequests++; json = { nodes, total: nodes.length, next_cursor: null }; }
    if (path === '/api/graph/edges') json = { edges, total: edges.length, next_cursor: null };
    if (path === '/api/temporal/bounds') json = { min: null, max: null };
    if (path === '/api/temporal/snapshot') json = { active_node_ids: nodes.map(n => n.id), active_node_count: nodes.length };
    if (path === '/api/graph/search') json = { results: [{ node: nodes[1], score: 1 }] };
    await route.fulfill({ json });
  });
  await page.goto(base);
  await page.getByRole('button', { name: 'Open Semantica Explorer' }).click();
  await graphSize(page, 80, 80);
  await page.waitForFunction(() => document.querySelector('button[aria-pressed="true"]')?.textContent !== undefined);
  assert.equal(await page.getByRole('button', { name: 'Grouped View', exact: true }).getAttribute('aria-pressed'), 'true');
  await page.locator('canvas').first().waitFor({ state: 'visible' });
  await mkdir('test-results', { recursive: true });
  await page.screenshot({ path: 'test-results/graph-filters-overview.png' });
  const type = page.getByLabel('Filter node type');
  const relation = page.getByLabel('Filter relationship type');
  const text = page.getByLabel('Filter node content');
  const clear = page.getByRole('button', { name: 'Clear filters' });
  await type.selectOption('Concept');
  await graphSize(page, 40, 40);
  await relation.selectOption('STUDIES');
  await graphSize(page, 0, 0);
  await page.getByText('No matches. Clear or change filters.', { exact: false }).waitFor();
  await clear.click();
  await graphSize(page, 80, 80);
  await relation.selectOption('RELATES');
  await graphSize(page, 40, 40);
  await text.fill('Topic 0');
  await graphSize(page, 0, 0);
  await clear.click();
  await graphSize(page, 80, 80);
  await text.fill('Topic 1');
  await graphSize(page, 11, 9);
  await clear.click();
  await graphSize(page, 80, 80);
  await type.selectOption('Concept');
  await graphSize(page, 40, 40);
  assert.equal(await text.inputValue(), '');
  assert.equal(nodeRequests, 1, 'scope changes reuse the immutable session input');
  await page.getByRole('button', { name: 'Reload graph data' }).click();
  await graphSize(page, 40, 40);
  await page.waitForFunction(() => !document.querySelector<HTMLSelectElement>('[aria-label="Filter node type"]')!.disabled);
  assert.equal(nodeRequests, 2, 'explicit reload fetches a fresh snapshot');
  await page.locator('.graph-stage-loader').waitFor({ state: 'hidden' });
  await page.screenshot({ path: 'test-results/graph-filters-scoped.png' });
  await page.setViewportSize({ width: 900, height: 800 });
  assert.ok(await page.getByRole('group', { name: 'Graph filters' }).evaluate(element => element.scrollWidth <= element.clientWidth));
  assert.deepEqual(writes, []);
  assert.deepEqual(errors, []);
});
