/**
 * src/workspaces/VocabularyWorkspace/Sidebar.tsx
 *
 * Left sidebar for the Vocabulary workspace.
 * - Lists available SKOS ConceptSchemes
 * - Shows the concept hierarchy tree for the active scheme
 * - Includes the import dropzone
 */
import { useState } from 'react';
import { useVocabularies, useConceptHierarchy } from './queries';
import { ConceptTree } from './ConceptTree';
import { ImportDropzone } from './ImportDropzone';
import type { ConceptNode, VocabularyScheme } from './types';

interface SidebarProps {
  onSelectConcept: (concept: ConceptNode) => void;
}

export function Sidebar({ onSelectConcept }: SidebarProps) {
  const { data: schemes = [], isLoading: schemesLoading } = useVocabularies();
  const [activeScheme, setActiveScheme] = useState<string | undefined>();

  // Auto-select first scheme
  const selectedSchemeUri = activeScheme ?? schemes[0]?.uri;

  const {
    data: hierarchy = [],
    isLoading: treeLoading,
  } = useConceptHierarchy(selectedSchemeUri);

  return (
    <div className="vocab-sidebar" style={{
      display: 'flex', flexDirection: 'column', minHeight: 0,
      borderRight: '1px solid var(--ws-border)',
      backgroundColor: 'var(--ws-bg)', overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '20px 20px 16px', flexShrink: 0,
        borderBottom: '1px solid var(--ws-border)',
      }}>
        <h2 style={{ fontSize: 18, color: 'var(--ws-text)', margin: '0 0 4px 0', fontWeight: 600 }}>
          Ontology & Vocabulary
        </h2>
        <p style={{ color: 'var(--ws-text-muted)', fontSize: 13, margin: 0 }}>
          {schemes.length
            ? `${schemes.length} vocabulary scheme${schemes.length > 1 ? 's' : ''}`
            : 'No vocabularies loaded'}
        </p>
      </div>

      {/* Scheme selector */}
      <div style={{ padding: '12px 16px', flexShrink: 0, borderBottom: '1px solid var(--ws-border)' }}>
        {schemesLoading ? (
          <div style={{ color: 'var(--ws-text-muted)', fontSize: 13 }}>Loading schemes…</div>
        ) : schemes.length === 0 ? (
          <div style={{ color: 'var(--ws-text-dim)', fontSize: 13, fontStyle: 'italic' }}>
            No schemes found. Import a .ttl or .rdf file below.
          </div>
        ) : (
          <select
            aria-label="Vocabulary scheme"
            value={selectedSchemeUri || ''}
            onChange={(e) => setActiveScheme(e.target.value)}
            style={{
              width: '100%',
              background: 'var(--ws-surface)',
              border: '1px solid var(--ws-border)',
              color: 'var(--ws-text)', padding: '8px 12px',
              borderRadius: 6, fontSize: 13, cursor: 'pointer',
            }}
          >
            {schemes.map((s: VocabularyScheme) => (
              <option key={s.uri} value={s.uri} style={{ background: 'var(--ws-bg)' }}>
                {s.label}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Concept Tree */}
      <div style={{
        flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}>
        {treeLoading ? (
          <div style={{ padding: 20, color: 'var(--ws-text-muted)', fontSize: 13, textAlign: 'center' }}>
            Loading hierarchy…
          </div>
        ) : hierarchy.length === 0 ? (
          <div style={{ padding: 20, color: 'var(--ws-text-dim)', fontSize: 13, textAlign: 'center', fontStyle: 'italic' }}>
            {selectedSchemeUri
              ? 'No concepts found in this scheme.'
              : 'Select a scheme to browse concepts.'}
          </div>
        ) : (
          <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
            <ConceptTree data={hierarchy} onSelectConcept={onSelectConcept} />
          </div>
        )}
      </div>

      {/* Import area */}
      <div style={{
        padding: '12px 16px', flexShrink: 0,
        borderTop: '1px solid var(--ws-border)',
      }}>
        <ImportDropzone />
      </div>
    </div>
  );
}
