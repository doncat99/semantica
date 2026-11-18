/**
 * src/workspaces/VocabularyWorkspace/PropertyPanel.tsx
 *
 * Detail panel for a selected SKOS concept — shows preferred label,
 * URI, alt labels, and description.
 */
import type { ConceptNode } from './types';

interface PropertyPanelProps {
  concept: ConceptNode | null;
}

export function PropertyPanel({ concept }: PropertyPanelProps) {
  if (!concept) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: '100%', color: 'var(--ws-text-muted)',
        textAlign: 'center', padding: 40,
      }}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
          strokeLinejoin="round" style={{ marginBottom: 16, opacity: 0.4 }}>
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
        </svg>
        <p style={{ fontSize: 15, fontWeight: 500, marginBottom: 4 }}>No concept selected</p>
        <p style={{ fontSize: 13 }}>Click a concept in the tree to view its properties.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 28, overflowY: 'auto', height: '100%' }}>
      {/* Header */}
      <div style={{ borderBottom: '1px solid var(--ws-border)', paddingBottom: 20, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <span style={{
            display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
            background: 'var(--ws-purple)', boxShadow: "none",
          }} />
          <span style={{ color: 'var(--ws-purple)', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            SKOS Concept
          </span>
        </div>
        <h2 style={{ margin: 0, color: 'var(--ws-text)', fontSize: 22, fontWeight: 700, wordBreak: 'break-word' }}>
          {concept.pref_label}
        </h2>
      </div>

      {/* URI Badge */}
      <div style={{
        marginBottom: 20, padding: '8px 14px',
        background: 'var(--ws-border)',
        border: '1px solid var(--ws-border)',
        borderRadius: 6, fontSize: 13, color: 'var(--ws-accent)',
        fontFamily: "'JetBrains Mono', monospace",
        wordBreak: 'break-all',
      }}>
        {concept.uri}
      </div>

      {/* Alt Labels */}
      {concept.alt_labels && concept.alt_labels.length > 0 && (
        <section style={{ marginBottom: 24 }}>
          <h4 style={{
            color: 'var(--ws-text-muted)', fontSize: 12, textTransform: 'uppercase',
            letterSpacing: '0.08em', marginBottom: 10,
          }}>
            Alternative Labels
          </h4>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {concept.alt_labels.map((lbl, i) => (
              <span key={i} style={{
                background: 'var(--ws-surface)', color: 'var(--ws-text)',
                padding: '4px 10px', borderRadius: 4, fontSize: 13,
                border: '1px solid var(--ws-surface-hover)',
              }}>
                {lbl}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Children summary */}
      <section style={{
        background: 'var(--ws-surface)', padding: 16, borderRadius: 8,
        border: '1px solid var(--ws-surface-hover)',
      }}>
        <h4 style={{
          color: 'var(--ws-text-muted)', fontSize: 12, textTransform: 'uppercase',
          letterSpacing: '0.08em', marginBottom: 10,
        }}>
          Narrower Concepts
        </h4>
        {concept.children && concept.children.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {concept.children.map((child) => (
              <span key={child.uri} style={{
                color: 'var(--ws-text)', fontSize: 13, padding: '6px 10px',
                background: 'var(--ws-border)', borderRadius: 4,
                border: '1px solid var(--ws-border)',
              }}>
                {child.pref_label}
              </span>
            ))}
          </div>
        ) : (
          <p style={{ margin: 0, color: 'var(--ws-text-dim)', fontStyle: 'italic', fontSize: 13 }}>
            Leaf concept — no narrower concepts.
          </p>
        )}
      </section>
    </div>
  );
}
