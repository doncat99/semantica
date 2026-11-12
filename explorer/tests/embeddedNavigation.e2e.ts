import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';
import test from 'node:test';
import { chromium } from 'playwright';

test('embedded native navigation retains graph filters, search and canvas across workspaces', async t => {
  const base = 'http://127.0.0.1:4187';
  const server = spawn('npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', '4187', '--strictPort'], { stdio: 'ignore' });
  t.after(() => server.kill());
  let ready = false;
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(base)).ok) { ready = true; break; } } catch { /* Starting preview. */ }
    await delay(100);
  }
  assert.ok(ready);
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    const observer = new MutationObserver(() => {
      if (document.documentElement) {
        document.documentElement.dataset.hostPresentation = 'true';
        observer.disconnect();
      }
    });
    observer.observe(document, { childList: true });
  });
  const nodes = [
    { id: 'a', type: 'Concept', content: 'Acoustic resonance', properties: {} },
    { id: 'b', type: 'Person', content: 'Researcher', properties: {} },
  ];
  const edges = [{ id: 'ab', familyId: 'ab', source: 'a', target: 'b', type: 'STUDIES', weight: 1, properties: {} }];
  let reads = 0;
  await page.routeWebSocket('**/ws/graph-updates', () => {});
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = {};
    if (path === '/api/info') json = { capabilities: { agent_memory: true } };
    if (path === '/api/native-scope') json = { available: true, active: { selection: {}, nodeCount: 2, linkCount: 1 } };
    if (path.startsWith('/api/native-scope/catalog')) json = { nodes: [], next_cursor: null };
    if (path === '/api/graph/stats') json = { node_count: 2, edge_count: 1 };
    if (path === '/api/graph/nodes') { reads++; json = { nodes, total: 2, next_cursor: null }; }
    if (path === '/api/graph/edges') json = { edges, total: 1, next_cursor: null };
    if (path === '/api/temporal/bounds') json = { min: null, max: null };
    if (path === '/api/temporal/snapshot') json = { active_node_ids: ['a', 'b'], active_node_count: 2 };
    await route.fulfill({ json });
  });
  await page.goto(base);
  const menu = page.getByRole('combobox', { name: 'Workspace', exact: true });
  await menu.waitFor();
  const title = page.getByRole('heading', { name: 'Knowledge Map', exact: true });
  await title.waitFor();
  const assertCompactNavigation = async () => {
    const headingBox = await title.boundingBox();
    const menuBox = await menu.boundingBox();
    assert.ok(headingBox && menuBox);
    assert.ok(headingBox.x + headingBox.width <= menuBox.x, 'heading and selector do not overlap');
    assert.ok(Math.abs(headingBox.y + headingBox.height / 2 - menuBox.y - menuBox.height / 2) < 2,
      'heading and selector share one row');
  };
  await assertCompactNavigation();
  await page.locator('canvas').first().waitFor({ state: 'visible' });
  assert.equal(await page.locator('.app-rail').count(), 0);
  assert.equal(await page.getByRole('heading', { name: 'Explore', exact: true }).count(), 0);
  assert.deepEqual(await menu.locator('option').evaluateAll(options => options.map(option => option.getAttribute('value'))),
    ['graph', 'vocabulary', 'memories', 'analyze', 'decisions', 'enrich', 'manage', 'ontology-hub']);
  const filter = page.getByLabel('Filter node content');
  await filter.fill('Acoustic');
  await page.getByRole('textbox', { name: 'Search graph nodes' }).fill('Acoustic');
  await page.locator('canvas').first().evaluate(canvas => { canvas.dataset.retainedCanvas = 'yes'; });
  await menu.selectOption('analyze');
  await page.getByRole('button', { name: 'SPARQL Querying', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Return to graph', exact: true }).click();
  assert.equal(await filter.inputValue(), 'Acoustic');
  assert.equal(await page.getByRole('textbox', { name: 'Search graph nodes' }).inputValue(), 'Acoustic');
  assert.equal(await page.locator('canvas').first().getAttribute('data-retained-canvas'), 'yes');
  assert.equal(reads, 1, 'workspace navigation does not refetch the graph');
  await mkdir('test-results', { recursive: true });
  await page.screenshot({ path: 'test-results/embedded-navigation-desktop.png' });
  await page.setViewportSize({ width: 760, height: 850 });
  await assertCompactNavigation();
  await menu.selectOption('vocabulary');
  assert.equal(await menu.inputValue(), 'vocabulary');
  await page.getByRole('button', { name: 'Return to graph', exact: true }).focus();
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector<HTMLSelectElement>('[aria-label="Workspace"]')?.value === 'graph');
  await page.screenshot({ path: 'test-results/embedded-navigation-narrow.png' });
  assert.deepEqual(errors, []);
});
