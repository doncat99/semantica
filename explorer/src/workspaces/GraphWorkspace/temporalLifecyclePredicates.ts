import type { GraphLoadSummary } from "./types";

/**
 * Predicates for gating GraphWorkspace temporal API requests.
 *
 * Temporal bounds and snapshot requests must strictly not execute until the
 * initial graph load has succeeded (summary !== undefined). An empty graph
 * (nodeCount: 0) is still a successful load and must not be rejected.
 */

export function shouldFetchTemporalBounds(
  summary: GraphLoadSummary | undefined,
  active = true,
): boolean {
  return active && summary !== undefined;
}

export function shouldFetchTemporalSnapshot({
  debouncedTime,
  active = true,
  isLoading,
  summary,
  temporalBoundsStatus,
}: {
  debouncedTime: Date | null;
  active?: boolean;
  isLoading: boolean;
  summary: GraphLoadSummary | undefined;
  temporalBoundsStatus: "loading" | "ready" | "none" | "error";
}): boolean {
  return (
    active &&
    summary !== undefined &&
    temporalBoundsStatus === "ready" &&
    debouncedTime !== null &&
    !isLoading
  );
}
