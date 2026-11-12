import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { chromium, type Page, type Frame } from "playwright";

const BASE_URL = "http://127.0.0.1:4175";
const initialNodes = [
  { id: "alice", type: "Person", content: "Alice", properties: {} },
  { id: "bob", type: "Person", content: "Bob", properties: {} },
  { id: "acme", type: "Organization", content: "Acme", properties: {} },
  { id: "london", type: "Location", content: "London", properties: {} },
  { id: "research", type: "Project", content: "Research", properties: {} },
  { id: "report", type: "Document", content: "Report", properties: {} },
];
const edges = [
  ["alice", "acme", "WORKS_AT"], ["bob", "acme", "WORKS_AT"],
  ["acme", "london", "LOCATED_IN"], ["alice", "research", "LEADS"],
  ["bob", "report", "AUTHORED"], ["report", "research", "DESCRIBES"],
].map(([source, target, type], i) => ({
  id: `edge_${i}`, familyId: `edge_${i}`, source, target, type, weight: 1, properties: {},
}));

async function assertLegendMatchesGraph(page: Page | Frame, nodeIds?: string[]) {
  const result = await page.evaluate(async (includedNodeIds) => {
    const storePath = "/src/store/graphStore.ts";
    const { graph } = await import(storePath);
    const colors: Record<string, string> = {};
    graph.forEachNode((id: string, attrs: { semanticGroup: string; baseColor: string }) => {
      if (includedNodeIds && !includedNodeIds.includes(id)) return;
      const hex = attrs.baseColor.replace("#", "");
      colors[attrs.semanticGroup] = `rgb(${[0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(", ")})`;
    });
    const items = [...document.querySelectorAll(".explore-color-legend-item")].map((item) => ({
      group: item.querySelector(".explore-color-legend-name")?.textContent,
      color: getComputedStyle(item.querySelector(".explore-color-legend-mark")!).backgroundColor,
    }));
    return { colors, items };
  }, nodeIds);
  assert.equal(result.items.length, Object.keys(result.colors).length);
  for (const item of result.items) {
    assert.equal(item.color, result.colors[item.group!], `Swatch for ${item.group} must match the loaded canvas color`);
  }
}

async function assertCanvasPixels(host: Page, page: Frame) {
  const png = await page.locator('canvas').first().screenshot();
  const coloredPixels = await host.evaluate(async data => {
    const image = new Image();
    image.src = `data:image/png;base64,${data}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.width; canvas.height = image.height;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(image, 0, 0);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] > 128 && Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) - Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) > 60) count++;
    }
    return count;
  }, png.toString('base64'));
  assert.ok(coloredPixels > 20, `Canvas must contain rendered semantic nodes, found ${coloredPixels} colored pixels`);
}

test("visible legend follows loaded data, reloads, focused views, and distance mode", async (t) => {
  const server = spawn("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", "4175", "--strictPort"], { stdio: "ignore" });
  t.after(() => { server.kill(); });
  let ready = false;
  for (let i = 0; i < 100; i += 1) {
    try { if ((await fetch(BASE_URL)).ok) { ready = true; break; } } catch { /* Starting Vite. */ }
    await delay(100);
  }
  assert.ok(ready, "Vite must start");
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      process.env.CHROMIUM_PATH || (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined),
  });
  t.after(() => browser.close());
  const host = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  host.setDefaultTimeout(30_000);
  const errors: string[] = [];
  host.on("pageerror", (error) => errors.push(error.message));
  host.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await host.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '', contentType: 'text/css' }));
  const light = { type: 'semantica:presentation', font: 'system-ui, sans-serif', colors: {
    'bg-app': '#f5f6f1', 'bg-panel': '#fcfcf9', 'bg-subtle': '#ecefe8', 'bg-elevated': '#ffffff',
    border: 'rgba(39, 49, 40, 0.15)', 'border-strong': 'rgba(39, 49, 40, 0.24)', text: '#273128',
    'text-strong': '#172019', 'text-muted': 'rgba(39, 49, 40, 0.68)', 'text-soft': 'rgba(39, 49, 40, 0.5)',
    accent: '#8aa363', 'accent-strong': '#6e8848', 'accent-soft': 'rgba(138, 163, 99, 0.18)', 'accent-contrast': '#172019', red: '#9c3e3a',
  } };
  const dark = { ...light, colors: { ...light.colors, 'bg-app': '#151916', 'bg-panel': '#202620',
    'bg-subtle': '#2b332b', 'bg-elevated': '#293129', text: '#e8eee4', 'text-strong': '#f4f7f0',
    'text-muted': '#b9c5b6', 'text-soft': '#a2b09e', border: 'rgba(232, 238, 228, 0.15)',
    'border-strong': 'rgba(232, 238, 228, 0.3)', 'accent-strong': '#b5cf8b' } };
  const embedded = new URL(BASE_URL);
  embedded.searchParams.set('hostOrigin', BASE_URL);
  await host.route(`${BASE_URL}/presentation-host`, route => route.fulfill({ contentType: 'text/html', body:
    `<html><body style="margin:0"><iframe title="Explorer" referrerpolicy="no-referrer" style="width:100vw;height:100vh;border:0" onload='this.contentWindow.postMessage(${JSON.stringify(light)}, ${JSON.stringify(BASE_URL)})' src="${embedded.href.replaceAll('&', '&amp;').replaceAll('"', '&quot;')}"></iframe></body></html>` }));
  let nodes = initialNodes;
  let graphRequests = 0;
  await host.routeWebSocket("**/ws/graph-updates", () => {});
  await host.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/graph/nodes' || path === '/api/graph/edges') graphRequests += 1;
    let json: unknown = {};
    if (path === "/api/info") json = { capabilities: { agent_memory: false } };
    if (path === "/api/graph/stats") json = { node_count: nodes.length, edge_count: edges.length };
    if (path === "/api/graph/nodes") json = { nodes, total: nodes.length, next_cursor: null };
    if (path === "/api/graph/edges") json = { edges, total: edges.length, next_cursor: null };
    if (path === "/api/temporal/bounds") json = { min: null, max: null };
    if (path === "/api/temporal/snapshot") json = { active_node_ids: nodes.map((n) => n.id), active_node_count: nodes.length };
    if (path === "/api/graph/search") json = { results: [{ node: nodes[0], score: 1 }] };
    await route.fulfill({ json });
  });
  await host.goto(`${BASE_URL}/presentation-host`, { waitUntil: 'domcontentloaded' });
  const page = await (await host.locator('iframe').elementHandle())!.contentFrame();
  assert.ok(page);
  await page.getByRole("button", { name: "Open Semantica Explorer" }).click();
  const legend = page.getByRole("group", { name: "Node colors" });
  try {
    await legend.waitFor();
  } catch (error) {
    console.error('Explorer browser errors:', errors);
    console.error('Explorer visible state:', await page.locator('body').innerText());
    console.error('Graph requests:', graphRequests);
    await host.screenshot({ path: 'test-results/host-presentation-failure.png', timeout: 10_000 });
    throw error;
  }
  await page.locator("canvas").first().waitFor({ state: "visible" });
  await assertLegendMatchesGraph(page);
  await page.getByRole('status').filter({ hasText: '6 / 6 nodes · 6 / 6 relationships' }).waitFor();
  assert.equal(await page.locator('.explore-status-strip').getByText('6 nodes · 6 edges', { exact: true }).count(), 0);
  assert.equal(await page.locator('.palantir-bg').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(245, 246, 241)');
  await assertCanvasPixels(host, page);
  await host.screenshot({ path: 'test-results/host-presentation-light.png' });
  assert.equal(await legend.getByText("Person", { exact: true }).count(), 1);
  assert.equal(await legend.getByText("Biomolecule", { exact: true }).count(), 0);

  nodes = initialNodes.map((node) => ({ ...node, type: node.type === "Person" ? "Researcher" : node.type }));
  await page.getByRole("button", { name: "Reload graph data" }).click();
  await legend.getByText("Researcher", { exact: true }).waitFor();
  assert.equal(await legend.getByText("Person", { exact: true }).count(), 0);
  await assertLegendMatchesGraph(page);

  await page.getByPlaceholder("Search command, node, or concept").fill("Alice");
  await page.getByRole("option").filter({ hasText: "Alice" }).click();
  const canvas = await page.locator('canvas').first().elementHandle();
  const beforeRequests = graphRequests;
  const beforePositions = await page.evaluate(async () => {
    const { graph } = await import('/src/store/graphStore.ts');
    return graph.mapNodes((id: string, attrs: { x: number; y: number; baseColor: string }) => [id, attrs.x, attrs.y, attrs.baseColor]);
  });
  // A same-origin message from the child itself must not impersonate its parent.
  await page.evaluate(value => window.postMessage(value, window.location.origin), dark);
  assert.equal(await page.locator('.palantir-bg').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(245, 246, 241)');
  await host.evaluate(value => document.querySelector('iframe')!.contentWindow!.postMessage(value, window.location.origin), dark);
  await page.waitForFunction(() => getComputedStyle(document.querySelector('.palantir-bg')!).backgroundColor === 'rgb(21, 25, 22)');
  assert.ok(await canvas!.evaluate(el => el.isConnected), 'Theme change must preserve the canvas instance');
  assert.equal(await page.getByRole('button', { name: 'Focus', exact: true }).isDisabled(), false, 'Selected node survives');
  assert.equal(graphRequests, beforeRequests, 'Theme change must not reload graph data');
  assert.deepEqual(await page.evaluate(async () => {
    const { graph } = await import('/src/store/graphStore.ts');
    return graph.mapNodes((id: string, attrs: { x: number; y: number; baseColor: string }) => [id, attrs.x, attrs.y, attrs.baseColor]);
  }), beforePositions);
  await assertLegendMatchesGraph(page);
  await assertCanvasPixels(host, page);
  await host.screenshot({ path: 'test-results/host-presentation-dark.png' });
  await host.evaluate(value => document.querySelector('iframe')!.contentWindow!.postMessage({ ...value, colors: { ...value.colors, 'bg-app': 'url(https://invalid.test)' } }, window.location.origin), light);
  await page.evaluate(value => window.dispatchEvent(new MessageEvent('message', {
    data: value, origin: 'https://foreign.test', source: window.parent,
  })), light);
  assert.equal(await page.locator('.palantir-bg').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(21, 25, 22)');
  await host.evaluate(value => document.querySelector('iframe')!.contentWindow!.postMessage(value, window.location.origin), light);
  await page.waitForFunction(() => getComputedStyle(document.querySelector('.palantir-bg')!).backgroundColor === 'rgb(245, 246, 241)');
  await host.setViewportSize({ width: 900, height: 1000 });
  await assertCanvasPixels(host, page);
  await host.screenshot({ path: 'test-results/host-presentation-narrow.png' });
  await host.setViewportSize({ width: 1440, height: 1000 });
  const heatmap = page.getByRole("button", { name: "Heatmap", exact: true });
  await heatmap.click();
  await legend.waitFor({ state: "hidden" });
  await heatmap.click();
  await legend.waitFor();
  await assertLegendMatchesGraph(page);
  const focusButton = page.getByRole("button", { name: "Focus", exact: true });
  assert.equal(await focusButton.isDisabled(), false, "Focus is enabled once a node is selected");
  await focusButton.click();
  await legend.getByText("Document", { exact: true }).waitFor({ state: "hidden" });
  await assertLegendMatchesGraph(page, ["alice", "acme", "research"]);
  assert.equal(await legend.getByText("Researcher", { exact: true }).count(), 1);
  await page.getByRole("button", { name: "Full Graph", exact: true }).click();
  await legend.getByText("Document", { exact: true }).waitFor();
  await assertLegendMatchesGraph(page);
  assert.deepEqual(errors, []);
});
