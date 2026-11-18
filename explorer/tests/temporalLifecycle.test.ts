import test from "node:test";
import assert from "node:assert/strict";

import {
  shouldFetchTemporalBounds,
  shouldFetchTemporalSnapshot,
} from "../src/workspaces/GraphWorkspace/temporalLifecyclePredicates.ts";
import type { GraphLoadSummary } from "../src/workspaces/GraphWorkspace/types.ts";
import { clearTemporalVisibility } from "../src/workspaces/GraphWorkspace/temporalSnapshotGuards.ts";

const sampleSummary: GraphLoadSummary = {
  nodeCount: 42,
  edgeCount: 78,
  loadTimeMs: 120,
  hasCoordinates: true,
  layoutSource: "provided",
  layoutReady: true,
};

const emptyGraphSummary: GraphLoadSummary = {
  nodeCount: 0,
  edgeCount: 0,
  loadTimeMs: 15,
  hasCoordinates: false,
  layoutSource: "runtime",
  layoutReady: false,
};

// ── shouldFetchTemporalBounds ────────────────────────────────────────────────

test("temporal bounds: false when summary is undefined (initial mount or failed load)", () => {
  assert.equal(
    shouldFetchTemporalBounds(undefined),
    false,
    "bounds request must not run before graph load succeeds",
  );
});

test("temporal bounds: true when non-empty summary is present", () => {
  assert.equal(
    shouldFetchTemporalBounds(sampleSummary),
    true,
    "bounds request should run when successful graph summary exists",
  );
});

test("temporal bounds: true when successful summary has nodeCount of 0", () => {
  assert.equal(
    shouldFetchTemporalBounds(emptyGraphSummary),
    true,
    "an empty graph is still a successful load and must allow bounds fetching",
  );
});

test("temporal requests stay disabled while the graph workspace is inactive", () => {
  assert.equal(shouldFetchTemporalBounds(sampleSummary, false), false);
  assert.equal(shouldFetchTemporalSnapshot({
    active: false,
    debouncedTime: new Date("2024-01-01T00:00:00Z"),
    isLoading: false,
    summary: sampleSummary,
    temporalBoundsStatus: "ready",
  }), false);
});

// ── shouldFetchTemporalSnapshot ──────────────────────────────────────────────

test("temporal snapshot: false when summary is undefined even if scrubber time is set and isLoading is false", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: false,
      summary: undefined,
      temporalBoundsStatus: "ready",
    }),
    false,
    "snapshot request must not run when graph load failed",
  );
});

test("temporal snapshot: false when graph is currently loading", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: true,
      summary: sampleSummary,
      temporalBoundsStatus: "ready",
    }),
    false,
    "snapshot request must not run while graph is loading",
  );
});

test("temporal snapshot: false when debouncedTime is null", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: null,
      isLoading: false,
      summary: sampleSummary,
      temporalBoundsStatus: "ready",
    }),
    false,
    "snapshot request must not run without a scrubber timestamp",
  );
});

test("temporal snapshot: true when summary exists, isLoading is false, and time is set", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: false,
      summary: sampleSummary,
      temporalBoundsStatus: "ready",
    }),
    true,
    "snapshot request should run after graph load succeeds and time is set",
  );
});

test("temporal snapshot: false until bounds confirm real temporal data", () => {
  assert.equal(shouldFetchTemporalSnapshot({
    debouncedTime: new Date("2024-01-01T00:00:00Z"),
    isLoading: false,
    summary: sampleSummary,
    temporalBoundsStatus: "loading",
  }), false);
  assert.equal(shouldFetchTemporalSnapshot({
    debouncedTime: new Date("2024-01-01T00:00:00Z"),
    isLoading: false,
    summary: sampleSummary,
    temporalBoundsStatus: "none",
  }), false);
  assert.equal(shouldFetchTemporalSnapshot({
    debouncedTime: new Date("2024-01-01T00:00:00Z"),
    isLoading: false,
    summary: sampleSummary,
    temporalBoundsStatus: "error",
  }), false);
});

test("graph changes clear temporal visibility from nodes and relationships", () => {
  const visibility = new Map<string, boolean>([["node:a", true], ["edge:a-b", true]]);
  const graph = {
    nodes: () => ["a"],
    edges: () => ["a-b"],
    setNodeAttribute: (id: string, _name: string, value: unknown) => visibility.set(`node:${id}`, Boolean(value)),
    setEdgeAttribute: (id: string, _name: string, value: unknown) => visibility.set(`edge:${id}`, Boolean(value)),
  };

  clearTemporalVisibility(graph);
  assert.equal(visibility.get("node:a"), false);
  assert.equal(visibility.get("edge:a-b"), false);
});

test("temporal snapshot: true when successful summary has 0 nodes, isLoading is false, and time is set", () => {
  assert.equal(
    shouldFetchTemporalSnapshot({
      debouncedTime: new Date("2024-01-01T00:00:00Z"),
      isLoading: false,
      summary: emptyGraphSummary,
      temporalBoundsStatus: "ready",
    }),
    true,
    "empty successful graph must allow snapshot requests once ready",
  );
});
