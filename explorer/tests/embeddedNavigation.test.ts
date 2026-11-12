import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');

test('embedded navigation replaces the global rail and graph heading in the native owner', () => {
  assert.match(source, /!embedded && <aside className="app-rail"/);
  assert.match(source, /aria-label="Workspace"/);
  assert.match(source, /hideHeader=\{embedded\}/);
  assert.match(source, /<h1 className="embedded-workspace-title">Knowledge Map<\/h1>/);
});

test('embedded graph has one retained owner, reset by scope and confirmed draft discard', () => {
  assert.match(source, /key=\{graphDraftRevision\}/);
  assert.match(source, /setGraphDraftRevision/);
  assert.match(source, /graphVisited \|\| graphActive/);
  assert.match(source, /inert=\{!graphActive\}/);
  assert.match(source, /key=\{nativeScopeRevision\}/);
});
