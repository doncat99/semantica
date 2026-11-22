import { GRAPH_THEME } from './workspaces/GraphWorkspace/graphTheme';

const COLOR_NAMES = ['bg-app', 'bg-panel', 'bg-subtle', 'bg-elevated', 'border', 'border-strong',
  'text', 'text-strong', 'text-muted', 'text-soft', 'accent', 'accent-strong', 'accent-soft',
  'accent-contrast', 'red'] as const;
export type Presentation = { type: 'semantica:presentation'; colors: Record<typeof COLOR_NAMES[number], string>; font: string };
export const PRESENTATION_CHANGED = 'semantica:presentation-changed';

export function applyPresentation(value: Presentation, root: HTMLElement) {
  const c = value.colors;
  const ui = GRAPH_THEME.ui;
  Object.assign(ui.text, { strong: c['text-strong'], body: c.text, muted: c['text-muted'], subtle: c['text-soft'], inverse: c['accent-contrast'] });
  Object.assign(ui.surface, { app: c['bg-app'], stage: c['bg-app'], card: c['bg-panel'], cardSubtle: c['bg-subtle'],
    cardStrong: c['bg-elevated'], panel: c['bg-panel'], panelBorder: c.border, divider: c.border, shadow: 'none' });
  Object.assign(ui.scene, { background: c['bg-app'], radialGlow: 'linear-gradient(transparent, transparent)',
    grid: 'transparent', gridStrong: 'transparent', vignette: 'none' });
  Object.assign(ui.control, { defaultBg: c['bg-panel'], defaultBorder: c.border, defaultText: c.text,
    hoverBg: c['bg-subtle'], activeBg: c['accent-soft'], activeBorder: c['accent-strong'], activeText: c['text-strong'],
    primaryBg: c.accent, primaryBorder: c['accent-strong'], primaryText: c['accent-contrast'], disabledText: c['text-soft'],
    inputBg: c['bg-elevated'], inputBorder: c.border, focusRing: c['accent-strong'], dangerText: c.red });
  Object.assign(ui.timeline, { background: c['bg-panel'], border: c.border, gridMinor: c.border, gridMajor: c['border-strong'],
    text: c['text-muted'], textStrong: c['text-strong'], playhead: c['accent-strong'], playheadSoft: c['accent-soft'] });
  for (const [group, values] of Object.entries(ui)) {
    for (const [name, color] of Object.entries(values)) root.style.setProperty(`--graph-${group}-${name}`, color);
  }
  const shell = { 'app-bg': c['bg-app'], 'panel-bg': c['bg-panel'], 'panel-border': c.border, 'text-main': c.text,
    'text-muted': c['text-muted'], accent: c.accent, 'accent-strong': c['accent-strong'], 'ws-bg': c['bg-app'],
    'ws-surface': c['bg-panel'], 'ws-surface-hover': c['bg-subtle'], 'ws-border': c.border, 'ws-border-strong': c['border-strong'],
    'ws-text': c.text, 'ws-text-muted': c['text-muted'], 'ws-text-dim': c['text-soft'], 'ws-accent': c['accent-strong'],
    'ws-accent-soft': c['accent-soft'], 'ws-green': 'color-mix(in srgb, #16834e 70%, var(--ws-text))',
    'ws-amber': 'color-mix(in srgb, #a45d08 70%, var(--ws-text))',
    'ws-red': c.red, 'ws-purple': 'color-mix(in srgb, #7546b2 70%, var(--ws-text))',
    'ws-radius': '8px', 'ws-radius-sm': '6px', 'ws-radius-lg': '8px', 'host-font': value.font };
  for (const [name, token] of Object.entries(shell)) root.style.setProperty(`--${name}`, token);
  Object.assign(GRAPH_THEME.palette.background, { canvas: c['bg-app'], shell: c['bg-panel'], shellBorder: c.border,
    shellGlow: 'transparent', grid: 'transparent', vignette: 'transparent', nodeBorder: c['bg-panel'] });
  Object.assign(GRAPH_THEME.palette.overview, { nodeBase: c['bg-panel'], nodeCore: c['text-muted'], nodeMuted: c['bg-subtle'],
    nodeBorder: c['border-strong'], edgeBackbone: c['text-muted'], edgeStructure: c.border, edgeInspection: c['border-strong'] });
  Object.assign(GRAPH_THEME.palette.muted, { edgeOverview: c.border, edgeStructure: c.border,
    edgeInspection: c['border-strong'], edgeFocus: c['text-muted'] });
  Object.assign(GRAPH_THEME.palette.accent, { selected: c['accent-strong'], hovered: c['accent-strong'] });
  GRAPH_THEME.nodes.selectedRing.color = c['accent-strong'];
  for (const label of [GRAPH_THEME.labels.chip, GRAPH_THEME.labels.hoverCard]) {
    Object.assign(label, { fontFamily: value.font, background: c['bg-elevated'], borderColor: c['border-strong'],
      textColor: c['text-strong'], shadowColor: 'transparent' });
  }
  GRAPH_THEME.labels.hoverCard.metaColor = c['text-muted'];
  root.dataset.hostPresentation = 'true';
  window.dispatchEvent(new Event(PRESENTATION_CHANGED));
}

