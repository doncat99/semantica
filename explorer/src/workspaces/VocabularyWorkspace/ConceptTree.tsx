/**
 * ConceptTree.tsx — react-arborist SKOS hierarchy viewer.
 *
 * Uses the workspace theme and measures the available scrolling viewport.
 */
import React, { useLayoutEffect, useRef, useState } from 'react';
import { Tree } from 'react-arborist';
import type { NodeRendererProps } from 'react-arborist';
import { ChevronRight, ChevronDown, Folder, FileText } from 'lucide-react';
import type { ConceptNode } from './types';

interface ConceptTreeProps {
  data: ConceptNode[];
  onSelectConcept: (concept: ConceptNode) => void;
}

export const ConceptTree: React.FC<ConceptTreeProps> = ({ data, onSelectConcept }) => {
  const container = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  useLayoutEffect(() => {
    const element = container.current!;
    const observer = new ResizeObserver(() => setHeight(element.clientHeight));
    observer.observe(element);
    setHeight(element.clientHeight);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={container} style={{
      height: '100%', width: '100%', minHeight: 0,
      backgroundColor: 'transparent',
      overflow: 'hidden',
    }}>
      {height > 0 && <Tree
        data={data}
        idAccessor="uri"
        width="100%"
        height={height}
        indent={24}
        rowHeight={36}
        childrenAccessor="children"
      >
        {(nodeProps: NodeRendererProps<ConceptNode>) => {
          const { node, style, dragHandle } = nodeProps;
          const isFolder = node.children && node.children.length > 0;

          return (
            <div
              ref={dragHandle}
              onClick={() => {
                node.toggle();
                onSelectConcept(node.data);
              }}
              style={{
                ...style,
                display: 'flex',
                alignItems: 'center',
                padding: '0 8px',
                cursor: 'pointer',
                backgroundColor: node.isSelected
                  ? 'var(--ws-border)'
                  : 'transparent',
                userSelect: 'none',
                borderBottom: '1px solid var(--ws-surface-hover)',
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!node.isSelected) {
                  (e.currentTarget as HTMLDivElement).style.background = 'var(--ws-border)';
                }
              }}
              onMouseLeave={(e) => {
                if (!node.isSelected) {
                  (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                }
              }}
            >
              <span style={{ width: 20, display: 'flex', justifyContent: 'center' }}>
                {isFolder ? (
                  node.isOpen
                    ? <ChevronDown size={14} color="var(--ws-text-muted)" />
                    : <ChevronRight size={14} color="var(--ws-text-muted)" />
                ) : null}
              </span>

              <span style={{ marginRight: 8, display: 'flex', alignItems: 'center' }}>
                {isFolder
                  ? <Folder size={14} color="var(--ws-purple)" />
                  : <FileText size={14} color="var(--ws-text-dim)" />
                }
              </span>

              <span style={{
                fontSize: 13, color: 'var(--ws-text)',
                whiteSpace: 'nowrap', overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}>
                {node.data.pref_label}
              </span>
            </div>
          );
        }}
      </Tree>}
    </div>
  );
};
