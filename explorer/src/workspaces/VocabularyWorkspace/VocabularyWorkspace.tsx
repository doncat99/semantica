/**
 * src/workspaces/VocabularyWorkspace/VocabularyWorkspace.tsx
 *
 * Main Vocabulary workspace — composes the Sidebar (scheme list + tree + import)
 * and the PropertyPanel (concept details) into a responsive two-column layout.
 *
 * All data fetching is handled by TanStack Query hooks in `queries.ts`.
 */
import { useState } from 'react';
import { Sidebar } from './Sidebar';
import { PropertyPanel } from './PropertyPanel';
import type { ConceptNode } from './types';

const THEME_CSS = `
  .vocab-workspace {
    display: flex;
    width: 100%;
    height: 100%;
    min-height: 0;
    background: var(--ws-bg);
    overflow: hidden;
  }
  .vocab-sidebar { width: 340px; flex: 0 0 340px; }
  .vocab-main {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
  }
  .vocab-main-content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }
  .vocab-detail-glass {
    background: var(--ws-surface);
    border: 1px solid var(--ws-border);
    min-height: 100%;
    box-sizing: border-box;
  }
  @media (max-width: 800px) {
    .vocab-sidebar { width: 42%; flex-basis: 42%; }
    .vocab-main-content { padding: 16px !important; }
  }
  @media (max-width: 520px) {
    .vocab-workspace { flex-direction: column; overflow-y: auto; }
    .vocab-sidebar { width: 100%; flex: 0 0 360px; }
    .vocab-main { flex: 0 0 auto; overflow: visible; }
    .vocab-main-content { overflow: visible; }
  }
`;

export function VocabularyWorkspace() {
  const [selectedConcept, setSelectedConcept] = useState<ConceptNode | null>(null);

  return (
    <div className="vocab-workspace">
      <style>{THEME_CSS}</style>

      {/* Left: Sidebar with scheme list + concept tree + import */}
      <Sidebar onSelectConcept={setSelectedConcept} />

      {/* Right: Concept detail panel */}
      <div className="vocab-main">
        <div className="vocab-main-content" style={{ padding: 32 }}>
          <div className="vocab-detail-glass">
            <PropertyPanel concept={selectedConcept} />
          </div>
        </div>
      </div>
    </div>
  );
}
