import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Play, RotateCcw, CheckCircle2, AlertCircle, Zap, GitBranch } from "lucide-react";

const PAGE_SIZE = 100;
const TEMPLATES = [
  { label: "Drug Candidate", facts: `inhibits(Metformin, mTOR)\ncauses(mTOR, Neurodegeneration)\ntreats(Metformin, Diabetes)`, rule: `IF inhibits(Metformin, mTOR) AND causes(mTOR, Neurodegeneration) THEN candidate(Metformin, Alzheimer's)` },
  { label: "Gene → Disease", facts: `expressed_in(BRCA1, Breast)\nmutated_in(BRCA1, Cancer)\nassociated_with(Breast, Cancer)`, rule: `IF mutated_in(X, Cancer) AND expressed_in(X, Y) THEN risk_gene(X, Y)` },
  { label: "Pathway Activation", facts: `activates(EGF, EGFR)\ndownstream_of(MAPK, EGFR)\ndownstream_of(AKT, EGFR)`, rule: `IF activates(X, EGFR) AND downstream_of(Y, EGFR) THEN activates(X, Y)` },
];

interface Relation {
  id: string;
  source_id: string;
  source_label: string;
  target_id: string;
  target_label: string;
  type: string;
  fact: string;
}

interface RelationPage {
  relations: Relation[];
  relationship_types: Array<{ type: string; count: number }>;
  offset: number;
  total: number;
  has_more: boolean;
  skipped_edges: number;
}

export function ReasoningWorkspace() {
  const queryClient = useQueryClient();
  const [relations, setRelations] = useState<Relation[]>([]);
  const [selectedRelations, setSelectedRelations] = useState<Record<string, Relation>>({});
  const [relationshipTypes, setRelationshipTypes] = useState<RelationPage["relationship_types"]>([]);
  const [selectedType, setSelectedType] = useState("");
  const [pageOffset, setPageOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [skippedEdges, setSkippedEdges] = useState(0);
  const [facts, setFacts] = useState("");
  const [useManualFacts, setUseManualFacts] = useState(false);
  const [rules, setRules] = useState("");
  const [applyToGraph, setApplyToGraph] = useState(false);
  const [factsLoading, setFactsLoading] = useState(true);
  const [factsError, setFactsError] = useState("");
  const [result, setResult] = useState<{ inferred_facts?: string[]; rules_fired?: number; added_edges?: number; mutated?: boolean } | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const ctrl = new AbortController();
    setFactsLoading(true);
    setFactsError("");
    const params = new URLSearchParams({ offset: String(pageOffset), limit: String(PAGE_SIZE) });
    if (selectedType) params.set("edge_type", selectedType);
    fetch(`/api/reason/facts?${params}`, { signal: ctrl.signal }).then(async response => {
      if (!response.ok) throw new Error(`Unable to load graph relationships: HTTP ${response.status}`);
      const data: RelationPage = await response.json();
      if (ctrl.signal.aborted) return;
      setRelations(current => pageOffset === 0 ? data.relations : [...current, ...data.relations]);
      setRelationshipTypes(data.relationship_types);
      setHasMore(data.has_more);
      setTotal(data.total);
      setSkippedEdges(data.skipped_edges);
    }).catch(loadError => {
      if (!ctrl.signal.aborted) setFactsError(loadError instanceof Error ? loadError.message : "Unable to load graph relationships");
    }).finally(() => {
      if (!ctrl.signal.aborted) setFactsLoading(false);
    });
    return () => ctrl.abort();
  }, [pageOffset, selectedType]);

  const labelByNodeId = useMemo(() => {
    const labels = new Map<string, string>();
    Object.values(selectedRelations).forEach(relation => {
      labels.set(relation.source_id, relation.source_label);
      labels.set(relation.target_id, relation.target_label);
    });
    return labels;
  }, [selectedRelations]);
  const selectedFacts = useMemo(() => Object.values(selectedRelations).map(relation => relation.fact), [selectedRelations]);

  async function handleRun() {
    setIsRunning(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch("/api/reason", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          facts: (useManualFacts ? facts : selectedFacts.join("\n")).split(/\r?\n/).map(line => line.trim()).filter(Boolean),
          rules: rules.split(/\r?\n/).map(line => line.trim()).filter(Boolean),
          mode: "forward",
          apply_to_graph: applyToGraph,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `Status ${response.status}`);
      if (response.status === 207) setError(data.message || "Warning: Partial success reasoning.");
      setResult(data);
      if (data.mutated) queryClient.invalidateQueries({ queryKey: ["graph", "full-load"] });
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Reasoning failed");
    } finally {
      setIsRunning(false);
    }
  }

  function toggleRelation(relation: Relation) {
    setSelectedRelations(current => {
      const next = { ...current };
      if (next[relation.id]) delete next[relation.id];
      else next[relation.id] = relation;
      return next;
    });
    setResult(null);
  }

  function reset() {
    setFacts("");
    setUseManualFacts(false);
    setRules("");
    setSelectedRelations({});
    setResult(null);
    setError("");
  }

  function readableFact(fact: string) {
    return fact.replace(/\(([^,()]+),\s*([^,()]+)\)/, (_match, source: string, target: string) =>
      `(${labelByNodeId.get(source.trim()) ?? source.trim()}, ${labelByNodeId.get(target.trim()) ?? target.trim()})`);
  }

  const availableFacts = useManualFacts ? facts.trim() : selectedFacts.length > 0;
  return (
    <div className="ws-page" style={{ flexDirection: "row" }}>
      <div style={{ width: "min(520px, 52%)", minWidth: 340, flexShrink: 0, display: "flex", flexDirection: "column", borderRight: "1px solid var(--ws-border)", overflow: "hidden" }}>
        <div style={{ padding: "16px 18px 12px", borderBottom: "1px solid var(--ws-border)", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, background: "var(--ws-accent-soft)", border: "1px solid var(--ws-border-strong)", display: "grid", placeItems: "center", color: "var(--ws-accent)", flexShrink: 0 }}><BrainCircuit size={16} /></div>
            <div><div className="ws-eyebrow" style={{ marginBottom: 2 }}>Forward Chaining</div><div style={{ color: "var(--ws-text)", fontWeight: 700, fontSize: 15 }}>Inference Engine</div></div>
          </div>
        </div>

        <div className="ws-scroll ws-padded" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <section aria-labelledby="reasoning-relationships-title">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <h2 id="reasoning-relationships-title" className="ws-label" style={{ margin: 0 }}>Graph relationships</h2>
              <span className="ws-pill ws-pill--mono" style={{ marginLeft: "auto" }}>{Object.keys(selectedRelations).length} selected</span>
            </div>
            <label className="ws-label" htmlFor="relationship-type-filter">Relationship type</label>
            <select id="relationship-type-filter" aria-label="Filter relationship type" value={selectedType} onChange={event => { setSelectedType(event.target.value); setPageOffset(0); setRelations([]); }} style={{ width: "100%", marginBottom: 8 }}>
              <option value="">All types ({relationshipTypes.reduce((sum, item) => sum + item.count, 0)})</option>
              {relationshipTypes.map(item => <option key={item.type} value={item.type}>{item.type} ({item.count})</option>)}
            </select>
            {factsError && <div role="alert" className="ws-body">{factsError}</div>}
            <div role="list" aria-label="Available relationships" style={{ display: "flex", flexDirection: "column", border: "1px solid var(--ws-border)", borderRadius: "var(--ws-radius-sm)", overflow: "hidden", maxHeight: 310, overflowY: "auto" }}>
              {relations.map(relation => (
                <label key={relation.id} role="listitem" style={{ display: "grid", gridTemplateColumns: "18px minmax(0, 1fr)", gap: 8, alignItems: "center", padding: "8px 10px", borderBottom: "1px solid var(--ws-border)", cursor: "pointer" }}>
                  <input type="checkbox" aria-label={`Select ${relation.source_label} ${relation.type} ${relation.target_label}`} checked={Boolean(selectedRelations[relation.id])} onChange={() => toggleRelation(relation)} />
                  <span style={{ minWidth: 0, display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap", color: "var(--ws-text)", fontSize: 12, lineHeight: 1.4 }}>
                    <span>{relation.source_label}</span><span style={{ color: "var(--ws-text-dim)" }}>{relation.type}</span><span>{relation.target_label}</span>
                  </span>
                </label>
              ))}
              {relations.length === 0 && !factsLoading && <div className="ws-body" style={{ padding: 12 }}>{selectedType ? "No relationships of this type." : "No supported relationships in this graph."}</div>}
              {factsLoading && <div role="status" className="ws-body" style={{ padding: 12 }}>Loading relationships…</div>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <span className="ws-body">{relations.length} of {total} shown{skippedEdges ? ` · ${skippedEdges} unsupported on this page` : ""}</span>
              {hasMore && <button className="ws-btn ws-btn--ghost" style={{ marginLeft: "auto", padding: "5px 9px" }} disabled={factsLoading} onClick={() => setPageOffset(current => current + PAGE_SIZE)}>Load more</button>}
            </div>
          </section>

          <details>
            <summary className="ws-label" style={{ cursor: "pointer" }}>Advanced: enter facts manually</summary>
            <textarea className="ws-textarea" aria-label="Manual facts" value={facts} onChange={event => { setFacts(event.target.value); setUseManualFacts(true); }} rows={4} spellCheck={false} style={{ marginTop: 8 }} />
            <div className="ws-body" style={{ marginTop: 6 }}>Manual facts replace the selected graph relationships for this run.</div>
          </details>

          <section>
            <label className="ws-label" htmlFor="reasoning-rules">Rules</label>
            <div className="ws-body" style={{ marginBottom: 8 }}>Use <code style={{ color: "var(--ws-amber)", fontSize: 11 }}>IF … AND … THEN …</code>.</div>
            <textarea className="ws-textarea" id="reasoning-rules" aria-label="Rules" value={rules} onChange={event => setRules(event.target.value)} rows={5} spellCheck={false} />
          </section>

          <div>
            <div className="ws-eyebrow" style={{ marginBottom: 7 }}>Examples</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>{TEMPLATES.map(template => <button key={template.label} className="ws-btn ws-btn--ghost" style={{ padding: "5px 9px", fontSize: 11 }} onClick={() => { setFacts(template.facts); setUseManualFacts(true); setRules(template.rule); setResult(null); }}>{template.label}</button>)}</div>
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "9px 11px", borderRadius: "var(--ws-radius-sm)", border: "1px solid var(--ws-border)", background: applyToGraph ? "var(--ws-green-soft)" : "var(--ws-surface)" }}>
            <input type="checkbox" checked={applyToGraph} onChange={event => setApplyToGraph(event.target.checked)} />
            <span><span style={{ display: "block", fontSize: 13, fontWeight: 700, color: "var(--ws-text)" }}>Write inferred facts to graph</span><span style={{ fontSize: 11, color: "var(--ws-text-dim)" }}>Inferred binary facts are added as relationships</span></span>
          </label>

          <div style={{ display: "flex", gap: 8 }}>
            <button className="ws-btn ws-btn--primary" onClick={handleRun} disabled={isRunning || factsLoading || !availableFacts || !rules.trim()} style={{ flex: 1, justifyContent: "center" }}>{isRunning ? <><span className="ws-spin" style={{ display: "inline-block" }}><Zap size={15} /></span>Running…</> : <><Play size={14} />Run Reasoning</>}</button>
            <button className="ws-btn ws-btn--ghost" onClick={reset} title="Reset selected relationships and rules" aria-label="Reset"><RotateCcw size={14} /></button>
          </div>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid var(--ws-border)", flexShrink: 0, display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--ws-text)" }}>Inference Results</div>
          {result && !isRunning && <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}><span className="ws-pill ws-pill--accent"><Zap size={9} /> {result.rules_fired ?? 0} rules fired</span><span className="ws-pill ws-pill--green"><GitBranch size={9} /> {result.added_edges ?? 0} relationships added</span><span className="ws-pill ws-pill--mono">{result.mutated ? "graph updated" : "preview only"}</span></div>}
        </div>
        <div className="ws-scroll ws-padded" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {error && <div role="alert" className="ws-animate-in" style={{ display: "flex", gap: 10, padding: "12px 14px", borderRadius: "var(--ws-radius-sm)", background: "var(--ws-red-soft)", border: "1px solid var(--ws-red)", color: "var(--ws-red)", fontSize: 13 }}><AlertCircle size={16} style={{ flexShrink: 0 }} /><div>{error}</div></div>}
          {isRunning && <div role="status" className="ws-body">Applying rules to {useManualFacts ? facts.split(/\r?\n/).filter(Boolean).length : selectedFacts.length} facts…</div>}
          {result && !isRunning && ((result.inferred_facts ?? []).length === 0 ? <div className="ws-empty"><div className="ws-empty-icon"><CheckCircle2 size={32} /></div><div className="ws-empty-title">Reasoning complete</div><div className="ws-empty-body">No new facts were inferred from the selected relationships and rules.</div></div> : <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{result.inferred_facts!.map((fact, index) => <div key={`${fact}-${index}`} style={{ padding: "11px 13px", borderRadius: "var(--ws-radius-sm)", background: "var(--ws-surface)", border: "1px solid var(--ws-border)", color: "var(--ws-text)", fontSize: 13 }}>{readableFact(fact)}</div>)}</div>)}
        </div>
      </div>
    </div>
  );
}
