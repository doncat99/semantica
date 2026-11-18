export interface ScrubberBoundsInput {
  minDate?: string | null;
  maxDate?: string | null;
}

export interface ScrubberBounds {
  minBound: Date;
  maxBound: Date;
  defaultTime: Date;
}

function parseBound(value: string | null | undefined): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function resolveScrubberBounds({ minDate, maxDate }: ScrubberBoundsInput): ScrubberBounds | null {
  const min = parseBound(minDate);
  const max = parseBound(maxDate);
  if (!min && !max) return null;

  const minBound = min ?? max!;
  const maxBound = max ?? min!;
  if (minBound > maxBound) return null;
  return { minBound, maxBound, defaultTime: maxBound };
}

/** Keeps a play-through at ~PLAY_FRAMES steps whatever the span, with a one-day floor. */
export function resolvePlayStepMs(minBound: Date, maxBound: Date): number {
  const span = maxBound.getTime() - minBound.getTime();
  return Math.max(1, Math.round(span / 60));
}
