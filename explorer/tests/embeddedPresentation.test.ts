import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';
import { initializeEmbeddedPresentation } from '../src/embeddedPresentation.ts';

test('authenticates the actual parent message without requiring a desktop Referrer', async () => {
  const dom = new JSDOM('<html></html>', { url: 'http://127.0.0.1:8123/?hostOrigin=ontoscience%3A%2F%2Fapp' });
  const parent = {};
  Object.defineProperty(dom.window, 'parent', { value: parent });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document,
    CSS: { supports: () => true }, Event: dom.window.Event });
  const colors = Object.fromEntries(['bg-app', 'bg-panel', 'bg-subtle', 'bg-elevated', 'border', 'border-strong',
    'text', 'text-strong', 'text-muted', 'text-soft', 'accent', 'accent-strong', 'accent-soft', 'accent-contrast', 'red']
    .map(key => [key, '#123456']));
  const presentation = { type: 'semantica:presentation', font: 'system-ui', colors };
  const send = (origin: string, source: unknown, data: unknown) => dom.window.dispatchEvent(
    new dom.window.MessageEvent('message', { origin, source: source as Window, data }));
  try {
    assert.equal(document.referrer, '');
    const ready = initializeEmbeddedPresentation();
    send('https://attacker.example', parent, presentation);
    send('ontoscience://app', {}, presentation);
    send('ontoscience://app', parent, { ...presentation, font: 'bad; font' });
    assert.equal(document.documentElement.dataset.hostPresentation, undefined);
    send('ontoscience://app', parent, presentation);
    await ready;
    assert.equal(document.documentElement.dataset.hostPresentation, 'true');
    send('ontoscience://app', parent, { ...presentation, colors: { ...colors, 'bg-app': '#abcdef' } });
    assert.equal(document.documentElement.style.getPropertyValue('--app-bg'), '#abcdef');
  } finally { dom.window.close(); }
});
