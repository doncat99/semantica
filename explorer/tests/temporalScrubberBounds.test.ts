import test from "node:test";
import assert from "node:assert/strict";

import {
  resolvePlayStepMs,
  resolveScrubberBounds,
} from "../src/workspaces/GraphWorkspace/temporalScrubberBounds.ts";

test("undated graphs have no playable bounds", () => {
  assert.equal(resolveScrubberBounds({}), null);
  assert.equal(resolveScrubberBounds({ minDate: "bad", maxDate: "also bad" }), null);
});

test("a single effective date is not extended to the current date", () => {
  const bounds = resolveScrubberBounds({ minDate: "2026-01-15T00:00:00Z" });
  assert.ok(bounds);
  assert.equal(bounds.minBound.toISOString(), "2026-01-15T00:00:00.000Z");
  assert.equal(bounds.maxBound.toISOString(), "2026-01-15T00:00:00.000Z");
  assert.equal(bounds.defaultTime.toISOString(), "2026-01-15T00:00:00.000Z");
});

test("range and initial time use the real reported dates", () => {
  const bounds = resolveScrubberBounds({
    minDate: "2020-01-01T00:00:00Z",
    maxDate: "2030-01-01T00:00:00Z",
  });
  assert.ok(bounds);
  assert.equal(bounds.defaultTime.toISOString(), "2030-01-01T00:00:00.000Z");
});

test("play step divides the actual span into about sixty frames", () => {
  const min = new Date("2020-01-01T00:00:00Z");
  const max = new Date("2030-01-01T00:00:00Z");
  const frames = (max.getTime() - min.getTime()) / resolvePlayStepMs(min, max);
  assert.ok(frames > 50 && frames < 70);
});
