export type DimensionFrameLabelKind = "extent" | "tick" | "title";
export type DimensionFrameLabelAxis = "x" | "y" | "z";

export interface DimensionFramePixelRect {
  bottom: number;
  left: number;
  right: number;
  top: number;
}

export interface DimensionFrameProjectedPoint {
  /** Normalized device coordinates after camera projection. */
  x: number;
  y: number;
  z: number;
}

export interface DimensionFrameLabelCandidate {
  axis: DimensionFrameLabelAxis;
  bounds: DimensionFramePixelRect;
  key: string;
  kind: DimensionFrameLabelKind;
  tickIndex?: number;
  tickStride?: number;
}

export interface DimensionFramePixelSize {
  height: number;
  width: number;
}

/**
 * Encloses all camera-visible corners of the projected frame. Using every
 * corner avoids the diagonal collapse possible when only min/max are tested.
 */
export function dimensionFrameBoundsFromProjectedCorners(
  corners: readonly DimensionFrameProjectedPoint[],
  viewport: DimensionFramePixelSize,
): DimensionFramePixelRect | null {
  if (viewport.width <= 0 || viewport.height <= 0) return null;
  const visible = corners.filter(
    (point) =>
      Number.isFinite(point.x) &&
      Number.isFinite(point.y) &&
      Number.isFinite(point.z) &&
      point.z >= -1 &&
      point.z <= 1,
  );
  if (visible.length === 0) return null;
  const pixels = visible.map((point) => ({
    x: ((point.x + 1) / 2) * viewport.width,
    y: ((1 - point.y) / 2) * viewport.height,
  }));
  return {
    bottom: Math.max(...pixels.map((point) => point.y)),
    left: Math.min(...pixels.map((point) => point.x)),
    right: Math.max(...pixels.map((point) => point.x)),
    top: Math.min(...pixels.map((point) => point.y)),
  };
}

/**
 * Resolve a non-overlapping, on-screen subset of dimension labels. New labels
 * need a small clearance before appearing; retained labels can approach to
 * touching without flickering around a single collision threshold.
 */
export function resolveDimensionFrameLabelVisibility(
  candidates: readonly DimensionFrameLabelCandidate[],
  viewport: DimensionFramePixelSize,
  previouslyVisible: ReadonlySet<string> = new Set(),
  compact = false,
  reservedHudRegions: readonly DimensionFramePixelRect[] = [],
): Set<string> {
  const tickExtrema = new Map<DimensionFrameLabelAxis, { max: number; min: number }>();
  for (const candidate of candidates) {
    if (candidate.kind !== "tick" || candidate.tickIndex === undefined) continue;
    const current = tickExtrema.get(candidate.axis);
    tickExtrema.set(candidate.axis, {
      max: current ? Math.max(current.max, candidate.tickIndex) : candidate.tickIndex,
      min: current ? Math.min(current.min, candidate.tickIndex) : candidate.tickIndex,
    });
  }

  const ordered = candidates
    .map((candidate, index) => ({
      candidate,
      index,
      priority: labelPriority(candidate, tickExtrema),
    }))
    .sort((left, right) => {
      if (left.priority !== right.priority) return right.priority - left.priority;
      const leftWasVisible = previouslyVisible.has(left.candidate.key);
      const rightWasVisible = previouslyVisible.has(right.candidate.key);
      if (leftWasVisible !== rightWasVisible) return leftWasVisible ? -1 : 1;
      return left.index - right.index;
    });

  const accepted: DimensionFramePixelRect[] = [];
  const visible = new Set<string>();
  for (const { candidate, priority } of ordered) {
    if (!isInsideViewport(candidate.bounds, viewport)) continue;
    if (reservedHudRegions.some((region) => overlaps(candidate.bounds, region))) continue;
    if (compact && candidate.kind === "tick" && priority < 200) continue;
    if (
      candidate.kind === "tick" &&
      candidate.tickIndex !== undefined &&
      priority < 200 &&
      candidate.tickIndex % Math.max(candidate.tickStride ?? 1, 1) !== 0
    ) {
      continue;
    }
    const clearance = previouslyVisible.has(candidate.key) ? 0 : 4;
    if (accepted.some((other) => overlapsWithClearance(candidate.bounds, other, clearance))) {
      continue;
    }
    visible.add(candidate.key);
    accepted.push(candidate.bounds);
  }
  return visible;
}

function labelPriority(
  candidate: DimensionFrameLabelCandidate,
  tickExtrema: ReadonlyMap<DimensionFrameLabelAxis, { max: number; min: number }>,
): number {
  if (candidate.kind === "title") return 400;
  if (candidate.kind === "tick" && candidate.tickIndex === 0) return 300;
  if (candidate.kind === "extent") return 260;
  if (candidate.kind === "tick" && candidate.tickIndex !== undefined) {
    const extrema = tickExtrema.get(candidate.axis);
    if (
      extrema &&
      (candidate.tickIndex === extrema.min || candidate.tickIndex === extrema.max)
    ) {
      return 200;
    }
  }
  return 100;
}

function isInsideViewport(
  rect: DimensionFramePixelRect,
  viewport: DimensionFramePixelSize,
): boolean {
  return (
    rect.left >= 0 &&
    rect.top >= 0 &&
    rect.right <= viewport.width &&
    rect.bottom <= viewport.height
  );
}

function overlapsWithClearance(
  left: DimensionFramePixelRect,
  right: DimensionFramePixelRect,
  clearance: number,
): boolean {
  return overlaps(
    {
      bottom: left.bottom + clearance,
      left: left.left - clearance,
      right: left.right + clearance,
      top: left.top - clearance,
    },
    right,
  );
}

function overlaps(left: DimensionFramePixelRect, right: DimensionFramePixelRect): boolean {
  return !(
    left.right <= right.left ||
    right.right <= left.left ||
    left.bottom <= right.top ||
    right.bottom <= left.top
  );
}
