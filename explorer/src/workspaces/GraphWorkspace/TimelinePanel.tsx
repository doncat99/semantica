import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { DataSet } from "vis-data";
import { Timeline } from "vis-timeline";
import type { TimelineOptions } from "vis-timeline";
import "vis-timeline/styles/vis-timeline-graph2d.css";
import { GRAPH_UI } from "./graphTheme";
import { resolvePlayStepMs, resolveScrubberBounds } from "./temporalScrubberBounds";

export interface TimelinePanelProps {
  onTimeChange: (time: Date) => void;
  minDate?: string | null;
  maxDate?: string | null;
  availability: "loading" | "ready" | "none" | "error";
}

const PLAYHEAD_ID = "playhead";
const PLAY_INTERVAL_MS = 500;

const VIS_OVERRIDE_CSS = `
  .sem-timeline-wrap .vis-timeline { border: none !important; background: transparent !important; overflow: visible !important; }
  .sem-timeline-wrap .vis-panel.vis-background, .sem-timeline-wrap .vis-panel.vis-center { background: transparent !important; }
  .sem-timeline-wrap .vis-panel { border-color: ${GRAPH_UI.timeline.border} !important; }
  .sem-timeline-wrap .vis-time-axis .vis-text {
    color: ${GRAPH_UI.timeline.text} !important;
    font-size: 11px !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    padding-top: 3px !important;
  }
  .sem-timeline-wrap .vis-time-axis .vis-text.vis-major {
    color: ${GRAPH_UI.timeline.textStrong} !important;
    font-weight: 700 !important;
    font-size: 12px !important;
  }
  .sem-timeline-wrap .vis-time-axis .vis-grid.vis-minor { border-color: ${GRAPH_UI.timeline.gridMinor} !important; }
  .sem-timeline-wrap .vis-time-axis .vis-grid.vis-major { border-color: ${GRAPH_UI.timeline.gridMajor} !important; }
  .sem-timeline-wrap .vis-custom-time.${PLAYHEAD_ID} {
    background: ${GRAPH_UI.timeline.playheadSoft} !important;
    width: 2px !important;
    cursor: ew-resize !important;
    z-index: 5 !important;
  }
  .sem-timeline-wrap .vis-custom-time.${PLAYHEAD_ID} > .vis-custom-time-marker {
    background: ${GRAPH_UI.timeline.playhead} !important;
    color: ${GRAPH_UI.text.inverse} !important;
    font-size: 10px !important;
    font-weight: 700 !important;
    border-radius: 3px !important;
    padding: 1px 5px !important;
    white-space: nowrap !important;
    box-shadow: 0 0 8px rgba(98, 226, 205, 0.45) !important;
  }
  .sem-timeline-wrap .vis-current-time { display: none !important; }
  .sem-timeline-wrap .vis-panel.vis-left { display: none !important; }
`;

function formatPlayheadLabel(value: Date): string {
  return `${value.getFullYear()}/${String(value.getMonth() + 1).padStart(2, "0")}`;
}

export function TimelinePanel({ onTimeChange, minDate, maxDate, availability }: TimelinePanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<Timeline | null>(null);
  const playheadRef = useRef<Date | null>(null);
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [displayDate, setDisplayDate] = useState("");

  // Captured once per mount so re-renders keep the same reference and do not
  // retrigger the timeline effect below.
  const bounds = useMemo(() => resolveScrubberBounds({ minDate, maxDate }), [maxDate, minDate]);
  const canPlay = availability === "ready" && bounds !== null
    && bounds.maxBound.getTime() > bounds.minBound.getTime();

  useEffect(() => {
    if (playIntervalRef.current) {
      clearInterval(playIntervalRef.current);
      playIntervalRef.current = null;
    }
    setIsPlaying(false);
    if (availability !== "ready" || !bounds || !containerRef.current) {
      timelineRef.current?.destroy();
      timelineRef.current = null;
      playheadRef.current = null;
      setDisplayDate("");
      return;
    }

    const { minBound, maxBound, defaultTime } = bounds;
    const items = new DataSet([]);
    const options: TimelineOptions = {
      height: "100%",
      min: minBound,
      max: maxBound,
      start: minBound,
      end: maxBound,
      showCurrentTime: false,
      zoomable: true,
      moveable: true,
      zoomMin: 1,
      zoomMax: 1000 * 60 * 60 * 24 * 365 * 80,
      showMajorLabels: true,
      showMinorLabels: true,
      orientation: { axis: "bottom" },
      margin: { item: 0, axis: 0 },
      selectable: false,
      stack: false,
    } as TimelineOptions;

    const timeline = new Timeline(containerRef.current, items, options);
    timelineRef.current = timeline;
    playheadRef.current = defaultTime;
    timeline.addCustomTime(defaultTime, PLAYHEAD_ID);
    timeline.on("timechange", (props: { id: string; time: Date }) => {
      if (props.id !== PLAYHEAD_ID) return;
      playheadRef.current = props.time;
      timeline.setCustomTime(props.time, PLAYHEAD_ID);
      onTimeChange(props.time);
      setDisplayDate(formatPlayheadLabel(props.time));
    });
    onTimeChange(defaultTime);
    setDisplayDate(formatPlayheadLabel(defaultTime));
    return () => {
      timeline.destroy();
      if (timelineRef.current === timeline) timelineRef.current = null;
    };
  }, [availability, bounds, onTimeChange]);

  const startPlay = useCallback(() => {
    if (playIntervalRef.current) return;
    playIntervalRef.current = setInterval(() => {
      const timeline = timelineRef.current;
      if (!timeline) return;
      if (!playheadRef.current || !bounds) return;
      const next = new Date(playheadRef.current.getTime() + resolvePlayStepMs(bounds.minBound, bounds.maxBound));
      if (next >= bounds.maxBound) {
        next.setTime(bounds.minBound.getTime());
      }
      playheadRef.current = next;
      timeline.setCustomTime(next, PLAYHEAD_ID);
      onTimeChange(next);
      setDisplayDate(formatPlayheadLabel(next));
    }, PLAY_INTERVAL_MS);
  }, [bounds, onTimeChange]);

  const stopPlay = useCallback(() => {
    if (playIntervalRef.current) {
      clearInterval(playIntervalRef.current);
      playIntervalRef.current = null;
    }
  }, []);

  const togglePlay = useCallback(() => {
    setIsPlaying((previous) => {
      if (previous) {
        stopPlay();
        return false;
      }
      startPlay();
      return true;
    });
  }, [canPlay, startPlay, stopPlay]);

  useEffect(() => () => stopPlay(), [stopPlay]);

  return (
    <div style={{ position: "relative", width: "100%", height: "90px", borderTop: `1px solid ${GRAPH_UI.timeline.border}`, background: GRAPH_UI.timeline.background, backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)", display: "flex", alignItems: "stretch", flexShrink: 0 }}>
      <style>{VIS_OVERRIDE_CSS}</style>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4, padding: "0 16px", borderRight: `1px solid ${GRAPH_UI.timeline.border}`, minWidth: 80, flexShrink: 0 }}>
        <button
          id="temporal-play-btn"
          onClick={togglePlay}
          disabled={!canPlay}
          title={isPlaying ? "Pause Evolution" : "Play Evolution"}
          style={{ width: 34, height: 34, borderRadius: "50%", border: `1.5px solid ${isPlaying ? GRAPH_UI.control.activeBorder : GRAPH_UI.control.defaultBorder}`, background: isPlaying ? GRAPH_UI.timeline.playheadSoft : GRAPH_UI.control.defaultBg, color: GRAPH_UI.timeline.playhead, cursor: canPlay ? "pointer" : "not-allowed", opacity: canPlay ? 1 : 0.45, display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.2s", boxShadow: isPlaying ? "0 0 10px rgba(98, 226, 205, 0.32)" : "none" }}
        >
          {isPlaying ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21" /></svg>
          )}
        </button>
        <span style={{ fontSize: 10, color: isPlaying ? GRAPH_UI.timeline.playhead : GRAPH_UI.timeline.text, fontFamily: "monospace", letterSpacing: "0.04em", transition: "color 0.2s" }}>
          {availability === "loading" ? "Loading time data…" : null}
          {availability === "none" ? "此圖譜尚無可用的時間資料" : null}
          {availability === "error" ? "Unable to load time data" : null}
          {availability === "ready" ? displayDate : null}
        </span>
      </div>

      <div style={{ position: "absolute", top: 5, left: 100, fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", color: GRAPH_UI.text.subtle, textTransform: "uppercase", pointerEvents: "none", zIndex: 2 }}>
        {availability === "ready" && bounds ? `Temporal Scrubber · ${bounds.minBound.getFullYear()}-${bounds.maxBound.getFullYear()}` : "Temporal Scrubber"}
      </div>

      <div className="sem-timeline-wrap" style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {availability === "ready" ? <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative" }} /> : null}
      </div>
    </div>
  );
}
