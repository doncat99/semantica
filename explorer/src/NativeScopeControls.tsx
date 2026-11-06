import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

type CatalogKind = 'sources' | 'communities';
type CatalogPage = { nodes: Array<{ id: string; memberCount?: number }>; next_cursor: string | null };
type Selection = { sourceId?: string; communityId?: string; nodeIds?: string[]; after?: string };
type Active = { selection: Selection; next_cursor: string | null; nodeCount: number; linkCount: number };

async function read<T>(url: string, signal: AbortSignal, selection?: Selection): Promise<T> {
  const response = await fetch(url, { signal, ...(selection ? { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(selection) } : {}) });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Native scene request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

/** Explicit input to existing native algorithms; no automatic project traversal. */
export function NativeScopeControls({ onChange }: { onChange: () => void }) {
  const client = useQueryClient();
  const [available, setAvailable] = useState(false);
  const [kind, setKind] = useState<CatalogKind>('sources');
  const [catalog, setCatalog] = useState<CatalogPage>({ nodes: [], next_cursor: null });
  const [chosen, setChosen] = useState('');
  const [ids, setIds] = useState('');
  const [active, setActive] = useState<Active | null>(null);
  const [history, setHistory] = useState<Selection[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void fetch('/api/native-scope', { signal: controller.signal }).then(async response => {
      if (response.status === 404) return;
      if (!response.ok) throw new Error('Native scope is unavailable');
      const status = await response.json() as { available: boolean; active: Active | null };
      setAvailable(status.available); setActive(status.active);
      setCatalog(await read<CatalogPage>('/api/native-scope/catalog?kind=sources', controller.signal));
    }).catch((cause: unknown) => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => { controller.abort(); pending.current?.abort(); };
  }, []);
  async function perform(work: (signal: AbortSignal) => Promise<void>) {
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError('');
    try { await work(controller.signal); }
    catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { if (pending.current === controller) { pending.current = null; setBusy(false); } }
  }
  async function browse(nextKind: CatalogKind, after?: string) {
    await perform(async signal => {
      setCatalog(await read<CatalogPage>(`/api/native-scope/catalog?kind=${nextKind}${after ? `&after=${encodeURIComponent(after)}` : ''}`,signal));
      setKind(nextKind); setChosen('');
    });
  }
  async function select(selection: Selection, nextHistory: Selection[] = []) {
    if (nextHistory.length > 64) { setError('Navigation history is limited to 64 pages. Open a new scope or explicit node set.'); return; }
    await perform(async signal => {
      const result = await read<Active>('/api/native-scope/select',signal,selection);
      await client.cancelQueries(); client.clear();
      setActive(result); setHistory(nextHistory);
      // Remount existing owners after clearing the old scene's query cache.
      onChange();
    });
  }
  if (!available) return error ? <div role="alert">{error}</div> : null;
  return <section aria-label="Native graph scope" style={{ padding: '10px 16px', borderBottom: '1px solid var(--ws-border)',
    color: 'var(--ws-text)', background: 'var(--ws-bg)', fontSize: 12, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
    <label>Browse <select aria-label="Scope kind" value={kind} disabled={busy}
      onChange={event => void browse(event.target.value as CatalogKind)}>
      <option value="sources">Sources</option><option value="communities">Communities</option>
    </select></label>
    <select aria-label="Select native scope" value={chosen} onChange={event => setChosen(event.target.value)} disabled={busy} style={{ maxWidth: 280 }}>
      <option value="">Choose a scope</option>
      {catalog.nodes.map(node => <option key={node.id} value={node.id}>{node.id}{node.memberCount !== undefined ? ` (${node.memberCount} members)` : ''}</option>)}
    </select>
    <button disabled={busy || !chosen} onClick={() => void select(kind === 'sources' ? { sourceId: chosen } : { communityId: chosen })}>Open first node page</button>
    <button disabled={busy || !catalog.next_cursor} onClick={() => void browse(kind,catalog.next_cursor!)}>More scopes</button>
    <button disabled={busy} onClick={() => void browse(kind)}>First scopes</button>
    <label>Node IDs <input aria-label="Explicit native node identities" value={ids} onChange={event => setIds(event.target.value)} placeholder="Comma-separated IDs" /></label>
    <button disabled={busy || !ids.trim()} onClick={() => void select({ nodeIds: ids.split(',').map(id => id.trim()).filter(Boolean) })}>Open nodes</button>
    {active ? <>
      <span role="status">Node page {history.length + 1}: {active.nodeCount} nodes, {active.linkCount} links within this page{active.next_cursor ? '; more nodes available' : '; end of scope'}</span>
      <button disabled={busy || history.length === 0} onClick={() => void select(history[history.length - 1]!,history.slice(0,-1))}>Previous node page</button>
      <button disabled={busy || !active.next_cursor} onClick={() => void select({ ...active.selection, after: active.next_cursor! },[...history,active.selection])}>Next node page</button>
    </> : <span role="status">Choose a scope. No project graph is loaded.</span>}
    {busy && <button onClick={() => {
      // Keep awaiting the operation so a cancelled selection cannot be mistaken
      // for an installed scene, and do not allow another selection meanwhile.
      void fetch('/api/native-scope/cancel', { method: 'POST' });
    }}>Cancel selection</button>}
    {error && <span role="alert">{error}</span>}
  </section>;
}
