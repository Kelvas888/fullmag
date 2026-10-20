import type { Viewport3DBounds } from "../viewport3dRenderModel";
import type {
  Viewport3DCameraProjection,
  Viewport3DCameraState,
} from "../viewport3dStore";

export type DimensionFrameMode = "off" | "floor" | "cage";
export type DimensionFrameDensity = "auto" | "coarse" | "fine";
export type DimensionFrameUnitMode = "auto" | "nm" | "um" | "mm" | "m";
/** Which annotations sit on the frame edges: tick scales, overall extents, or both. */
export type DimensionFrameAnnotation = "ticks" | "extents" | "both";
export type DimensionFrameAxis = "x" | "y" | "z";
export type DimensionFrameOriginMode = "frame-center" | "world";

/** Discrete camera orientation used to choose the three annotated frame edges. */
export interface DimensionFrameCameraOrientation {
  xFacing: -1 | 1;
  yFacing: -1 | 1;
  zCornerX: -1 | 1;
  zCornerY: -1 | 1;
}
type DimensionFramePlaneId =
  | "xy-min"
  | "x-min"
  | "x-max"
  | "y-min"
  | "y-max";

export interface DimensionFrameOptions {
  annotation?: DimensionFrameAnnotation;
  bounds: Viewport3DBounds | null;
  cameraProjection: Viewport3DCameraProjection;
  cameraState?: Viewport3DCameraState;
  cameraOrientation?: DimensionFrameCameraOrientation;
  density: DimensionFrameDensity;
  labelsVisible: boolean;
  mode: DimensionFrameMode;
  originMode?: DimensionFrameOriginMode;
  unitMode: DimensionFrameUnitMode;
}

interface DimensionFramePlane {
  fixedAxis: DimensionFrameAxis;
  fixedValue: number;
  id: DimensionFramePlaneId;
  uAxis: DimensionFrameAxis;
  vAxis: DimensionFrameAxis;
}

export interface DimensionFrameUnit {
  factor: number;
  id: Exclude<DimensionFrameUnitMode, "auto">;
  label: string;
}

/**
 * A screen-space label pinned to a world point. The renderer projects
 * `outward` every frame to choose the text anchor and pushes the label
 * `pixelOffset` px away from the frame, so labels keep a constant size and
 * never sit on top of their tick.
 */
export interface DimensionFrameLabel {
  axis: DimensionFrameAxis;
  key: string;
  kind: "extent" | "tick" | "title";
  outward: [number, number, number];
  pixelOffset: number;
  position: [number, number, number];
  text: string;
  /** Major-step index from the selected frame or world origin. */
  tickIndex?: number;
  unitLabel?: string;
}

export interface DimensionFrameModel {
  annotation: DimensionFrameAnnotation;
  /** Three continuous scale edges, independent of labels and grid visibility. */
  axisLines: Float32Array;
  /** Physical bounds; the renderer projects all eight corners for HUD layout. */
  extent: [[number, number, number], [number, number, number]];
  extentLines: Float32Array;
  labels: DimensionFrameLabel[];
  majorLines: Float32Array;
  majorTickLines: Float32Array;
  minorLines: Float32Array;
  minorTickLines: Float32Array;
  mode: DimensionFrameMode;
  originMode: DimensionFrameOriginMode;
  planes: DimensionFramePlane[];
  signature: string;
  unit: DimensionFrameUnit;
}

interface ResolvedBounds {
  center: [number, number, number];
  max: [number, number, number];
  min: [number, number, number];
  size: [number, number, number];
}

const AXIS_INDEX: Record<DimensionFrameAxis, 0 | 1 | 2> = {
  x: 0,
  y: 1,
  z: 2,
};
const EMPTY_LINES = new Float32Array();
const FALLBACK_SIZE = 1e-6;
const LABEL_CAP = 36;
/** Tick mark lengths relative to the largest bounds span. */
const MAJOR_TICK_FRACTION = 0.024;
const MINOR_TICK_FRACTION = 0.012;
/** Offset of the extent dimension line from its edge, per annotation mode. */
const EXTENT_OFFSET_FRACTION: Record<DimensionFrameAnnotation, number> = {
  both: 0.2,
  extents: 0.07,
  ticks: 0,
};
/** Screen gaps in CSS px between the frame and its labels. */
const TICK_LABEL_GAP_PX = 5;
const TITLE_LABEL_GAP_PX = 40;
const EXTENT_LABEL_GAP_PX = 6;
const MAJOR_SEGMENT_CAP = 96;
const MINOR_SEGMENT_CAP = 240;
const MINOR_SUBDIVISIONS: Record<DimensionFrameDensity, number> = {
  auto: 4,
  coarse: 4,
  fine: 5,
};
const TARGET_INTERVALS: Record<DimensionFrameDensity, number> = {
  auto: 6,
  coarse: 4,
  fine: 10,
};

export function resolveDimensionFrameUnit(
  maxSpanMeters: number,
  unitMode: DimensionFrameUnitMode,
): DimensionFrameUnit {
  if (unitMode !== "auto") {
    return unitForId(unitMode);
  }
  if (maxSpanMeters < 2e-6) return unitForId("nm");
  if (maxSpanMeters < 2e-3) return unitForId("um");
  if (maxSpanMeters < 2) return unitForId("mm");
  return unitForId("m");
}

export function formatDimensionFrameTickValue(
  valueMeters: number,
  unit: DimensionFrameUnit,
): string {
  if (!Number.isFinite(valueMeters) || Math.abs(valueMeters) < 1e-18) {
    return "0";
  }
  const scaled = valueMeters * unit.factor;
  const rounded = Number(scaled.toPrecision(4));
  return rounded.toString();
}

export function resolveDimensionFrameStep(
  spanMeters: number,
  density: DimensionFrameDensity,
): number {
  const target = TARGET_INTERVALS[density];
  return niceStep(Math.max(spanMeters, 1e-18) / target);
}

export function buildDimensionFrameModel({
  annotation = "ticks",
  bounds,
  cameraOrientation,
  cameraState,
  density,
  labelsVisible,
  mode,
  originMode = "frame-center",
  unitMode,
}: DimensionFrameOptions): DimensionFrameModel {
  const resolvedBounds = resolveBounds(bounds);
  const maxSpan = Math.max(...resolvedBounds.size, 1e-18);
  const unit = resolveDimensionFrameUnit(maxSpan, unitMode);
  const orientation =
    cameraOrientation ??
    resolveDimensionFrameOrientationFromResolved(
      resolvedBounds,
      cameraState ?? DEFAULT_CAMERA_STATE,
    );
  if (mode === "off") {
    return emptyDimensionFrameModel(mode, unit, annotation, originMode);
  }

  const step = resolveDimensionFrameStep(maxSpan, density);
  const planes = resolveDimensionFramePlanes(mode, resolvedBounds, orientation);
  const minorStep = step / MINOR_SUBDIVISIONS[density];
  const majorLines: number[] = [];
  const minorLines: number[] = [];
  const axisLines = buildAxisLines(resolvedBounds, orientation);

  for (const plane of planes) {
    appendPlaneLines({
      bounds: resolvedBounds,
      lineBuffer: minorLines,
      maxSegments: MINOR_SEGMENT_CAP,
      originMode,
      plane,
      skipStep: step,
      step: minorStep,
    });
    appendPlaneLines({
      bounds: resolvedBounds,
      lineBuffer: majorLines,
      maxSegments: MAJOR_SEGMENT_CAP,
      originMode,
      plane,
      step,
    });
  }

  const annotations = labelsVisible
    ? buildEdgeAnnotations({
        annotation,
        bounds: resolvedBounds,
        orientation,
        maxSpan,
        minorStep,
        originMode,
        step,
        unit,
      })
    : EMPTY_ANNOTATIONS;

  return {
    annotation,
    axisLines: new Float32Array(axisLines),
    extent: [resolvedBounds.min, resolvedBounds.max],
    extentLines: new Float32Array(annotations.extentLines),
    labels: annotations.labels,
    majorLines: new Float32Array(majorLines),
    majorTickLines: new Float32Array(annotations.majorTickLines),
    minorLines: new Float32Array(minorLines),
    minorTickLines: new Float32Array(annotations.minorTickLines),
    mode,
    originMode,
    planes,
    signature: [
      mode,
      density,
      unit.id,
      annotation,
      labelsVisible ? "labels" : "nolabels",
      originMode,
      orientation.xFacing,
      orientation.yFacing,
      orientation.zCornerX,
      orientation.zCornerY,
      step,
      ...resolvedBounds.center,
      ...resolvedBounds.size,
      ...planes.map((plane) => plane.id),
      ...annotations.edgeIds,
    ].join(":"),
    unit,
  };
}

function resolveDimensionFramePlanes(
  mode: Exclude<DimensionFrameMode, "off">,
  bounds: ResolvedBounds,
  orientation: DimensionFrameCameraOrientation,
): DimensionFramePlane[] {
  const floor: DimensionFramePlane = {
    fixedAxis: "z",
    fixedValue: bounds.min[2],
    id: "xy-min",
    uAxis: "x",
    vAxis: "y",
  };
  if (mode === "floor") return [floor];

  const xWall: DimensionFramePlane =
    orientation.xFacing >= 0
      ? {
          fixedAxis: "x",
          fixedValue: bounds.min[0],
          id: "x-min",
          uAxis: "y",
          vAxis: "z",
        }
      : {
          fixedAxis: "x",
          fixedValue: bounds.max[0],
          id: "x-max",
          uAxis: "y",
          vAxis: "z",
        };
  const yWall: DimensionFramePlane =
    orientation.yFacing >= 0
      ? {
          fixedAxis: "y",
          fixedValue: bounds.min[1],
          id: "y-min",
          uAxis: "x",
          vAxis: "z",
        }
      : {
          fixedAxis: "y",
          fixedValue: bounds.max[1],
          id: "y-max",
          uAxis: "x",
          vAxis: "z",
        };

  return [floor, xWall, yWall];
}

function appendPlaneLines({
  bounds,
  lineBuffer,
  maxSegments,
  originMode,
  plane,
  skipStep,
  step,
}: {
  bounds: ResolvedBounds;
  lineBuffer: number[];
  maxSegments: number;
  originMode: DimensionFrameOriginMode;
  plane: DimensionFramePlane;
  skipStep?: number;
  step: number;
}) {
  const uIndex = AXIS_INDEX[plane.uAxis];
  const vIndex = AXIS_INDEX[plane.vAxis];
  const fixedIndex = AXIS_INDEX[plane.fixedAxis];
  for (const value of centeredTicksBetween({
    max: bounds.max[uIndex],
    min: bounds.min[uIndex],
    origin: tickOrigin(bounds, plane.uAxis, originMode),
    step,
  })) {
    if (
      skipStep &&
      isOnMajorStep(value - tickOrigin(bounds, plane.uAxis, originMode), skipStep)
    ) {
      continue;
    }
    if (lineBuffer.length / 6 >= maxSegments) return;
    pushSegment(
      lineBuffer,
      pointOnPlane(plane, fixedIndex, plane.fixedValue, uIndex, value, vIndex, bounds.min[vIndex]),
      pointOnPlane(plane, fixedIndex, plane.fixedValue, uIndex, value, vIndex, bounds.max[vIndex]),
    );
  }
  for (const value of centeredTicksBetween({
    max: bounds.max[vIndex],
    min: bounds.min[vIndex],
    origin: tickOrigin(bounds, plane.vAxis, originMode),
    step,
  })) {
    if (
      skipStep &&
      isOnMajorStep(value - tickOrigin(bounds, plane.vAxis, originMode), skipStep)
    ) {
      continue;
    }
    if (lineBuffer.length / 6 >= maxSegments) return;
    pushSegment(
      lineBuffer,
      pointOnPlane(plane, fixedIndex, plane.fixedValue, vIndex, value, uIndex, bounds.min[uIndex]),
      pointOnPlane(plane, fixedIndex, plane.fixedValue, vIndex, value, uIndex, bounds.max[uIndex]),
    );
  }
}

interface DimensionFrameEdge {
  axis: DimensionFrameAxis;
  /** Point on the edge at coordinate `value` along `axis`. */
  at: (value: number) => [number, number, number];
  id: string;
  outward: [number, number, number];
}

interface EdgeAnnotations {
  edgeIds: string[];
  extentLines: number[];
  labels: DimensionFrameLabel[];
  majorTickLines: number[];
  minorTickLines: number[];
}

const EMPTY_ANNOTATIONS: EdgeAnnotations = {
  edgeIds: [],
  extentLines: [],
  labels: [],
  majorTickLines: [],
  minorTickLines: [],
};

const AXIS_UNIT: Record<DimensionFrameAxis, [number, number, number]> = {
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1],
};

/**
 * Annotated edges follow the camera: x and y use the floor edges nearest the
 * viewer, z uses the vertical edge on the left of the silhouette. A fixed
 * `bounds.min` edge put the scale behind the object for half of all views.
 */
export function resolveDimensionFrameEdges(
  bounds: Pick<ResolvedBounds, "max" | "min">,
  cameraState: Viewport3DCameraState,
): DimensionFrameEdge[] {
  return resolveDimensionFrameEdgesForOrientation(
    bounds,
    resolveDimensionFrameOrientationFromResolved(bounds, cameraState),
  );
}

/**
 * Resolve camera-dependent edge selection as four discrete signs. The frame
 * geometry only needs to change when one of these signs flips during an orbit.
 */
export function resolveDimensionFrameOrientation(
  bounds: Viewport3DBounds | null,
  cameraState: Viewport3DCameraState,
): DimensionFrameCameraOrientation {
  return resolveDimensionFrameOrientationFromResolved(
    resolveBounds(bounds),
    cameraState,
  );
}

/**
 * Keep the currently selected frame edges while the camera is close to a
 * quadrant boundary. A new edge must win by a small angular margin before
 * the model changes, which avoids rapid swaps during slow orbit gestures.
 */
export function resolveDimensionFrameOrientationWithHysteresis(
  bounds: Viewport3DBounds | null,
  cameraState: Viewport3DCameraState,
  previous: DimensionFrameCameraOrientation,
  hysteresisDegrees = 4,
): DimensionFrameCameraOrientation {
  const resolvedBounds = resolveBounds(bounds);
  const toCamera = subtract(cameraState.position, cameraState.target);
  const length = Math.hypot(...toCamera);
  if (!Number.isFinite(length) || length < 1e-12) {
    return resolveDimensionFrameOrientationFromResolved(resolvedBounds, cameraState);
  }

  const degrees = Number.isFinite(hysteresisDegrees)
    ? Math.min(45, Math.max(0, hysteresisDegrees))
    : 4;
  const margin = Math.sin((degrees * Math.PI) / 180);
  const raw = resolveDimensionFrameOrientationFromResolved(resolvedBounds, cameraState);
  const right = screenRight(cameraState);
  const floorDiagonal = Math.hypot(
    resolvedBounds.max[0] - resolvedBounds.min[0],
    resolvedBounds.max[1] - resolvedBounds.min[1],
  );
  const previousCornerScore = cornerScreenScore(resolvedBounds, previous, right);
  const candidateCornerScore = cornerScreenScore(resolvedBounds, raw, right);
  const switchCorner =
    floorDiagonal <= 1e-12 ||
    candidateCornerScore + margin * floorDiagonal < previousCornerScore;

  return {
    xFacing: resolveHysteresisSign(toCamera[0] / length, previous.xFacing, margin),
    yFacing: resolveHysteresisSign(toCamera[1] / length, previous.yFacing, margin),
    zCornerX: switchCorner ? raw.zCornerX : previous.zCornerX,
    zCornerY: switchCorner ? raw.zCornerY : previous.zCornerY,
  };
}

function resolveHysteresisSign(
  normalizedComponent: number,
  previous: -1 | 1,
  margin: number,
): -1 | 1 {
  if (previous > 0) return normalizedComponent < -margin ? -1 : 1;
  return normalizedComponent > margin ? 1 : -1;
}

function cornerScreenScore(
  bounds: Pick<ResolvedBounds, "max" | "min">,
  orientation: DimensionFrameCameraOrientation,
  right: readonly [number, number],
): number {
  const x = orientation.zCornerX > 0 ? bounds.max[0] : bounds.min[0];
  const y = orientation.zCornerY > 0 ? bounds.max[1] : bounds.min[1];
  return x * right[0] + y * right[1];
}

const DEFAULT_CAMERA_STATE: Viewport3DCameraState = {
  position: [1, 1, 1],
  target: [0, 0, 0],
  up: [0, 0, 1],
};

function resolveDimensionFrameOrientationFromResolved(
  bounds: Pick<ResolvedBounds, "max" | "min">,
  cameraState: Viewport3DCameraState,
): DimensionFrameCameraOrientation {
  const toCamera = subtract(cameraState.position, cameraState.target);
  const right = screenRight(cameraState);
  const corners: Array<[number, number]> = [
    [bounds.min[0], bounds.min[1]],
    [bounds.max[0], bounds.min[1]],
    [bounds.max[0], bounds.max[1]],
    [bounds.min[0], bounds.max[1]],
  ];
  const [zx, zy] = corners.reduce((best, corner) =>
    corner[0] * right[0] + corner[1] * right[1] <
    best[0] * right[0] + best[1] * right[1] - 1e-24
      ? corner
      : best,
  );
  return {
    xFacing: toCamera[0] >= 0 ? 1 : -1,
    yFacing: toCamera[1] >= 0 ? 1 : -1,
    zCornerX: zx === bounds.max[0] ? 1 : -1,
    zCornerY: zy === bounds.max[1] ? 1 : -1,
  };
}

function resolveDimensionFrameEdgesForOrientation(
  bounds: Pick<ResolvedBounds, "max" | "min">,
  orientation: DimensionFrameCameraOrientation,
): DimensionFrameEdge[] {
  const xEdgeY = orientation.yFacing >= 0 ? bounds.max[1] : bounds.min[1];
  const yEdgeX = orientation.xFacing >= 0 ? bounds.max[0] : bounds.min[0];
  const floorZ = bounds.min[2];
  const xSign = orientation.yFacing;
  const ySign = orientation.xFacing;
  const zxSign = orientation.zCornerX;
  const zySign = orientation.zCornerY;
  const zx = zxSign > 0 ? bounds.max[0] : bounds.min[0];
  const zy = zySign > 0 ? bounds.max[1] : bounds.min[1];
  return [
    {
      axis: "x",
      at: (value) => [value, xEdgeY, floorZ],
      id: `x@${xSign > 0 ? "ymax" : "ymin"}`,
      outward: [0, xSign, 0],
    },
    {
      axis: "y",
      at: (value) => [yEdgeX, value, floorZ],
      id: `y@${ySign > 0 ? "xmax" : "xmin"}`,
      outward: [ySign, 0, 0],
    },
    {
      axis: "z",
      at: (value) => [zx, zy, value],
      id: `z@${zxSign > 0 ? "xmax" : "xmin"}${zySign > 0 ? "ymax" : "ymin"}`,
      outward: [zxSign * Math.SQRT1_2, zySign * Math.SQRT1_2, 0],
    },
  ];
}

function buildEdgeAnnotations({
  annotation,
  bounds,
  orientation,
  maxSpan,
  minorStep,
  originMode,
  step,
  unit,
}: {
  annotation: DimensionFrameAnnotation;
  bounds: ResolvedBounds;
  orientation: DimensionFrameCameraOrientation;
  maxSpan: number;
  minorStep: number;
  originMode: DimensionFrameOriginMode;
  step: number;
  unit: DimensionFrameUnit;
}): EdgeAnnotations {
  const result: EdgeAnnotations = {
    edgeIds: [],
    extentLines: [],
    labels: [],
    majorTickLines: [],
    minorTickLines: [],
  };
  const showTicks = annotation !== "extents";
  const showExtents = annotation !== "ticks";
  const majorLength = maxSpan * MAJOR_TICK_FRACTION;
  const minorLength = maxSpan * MINOR_TICK_FRACTION;
  let tickLabelCount = 0;

  for (const edge of resolveDimensionFrameEdgesForOrientation(bounds, orientation)) {
    const index = AXIS_INDEX[edge.axis];
    const min = bounds.min[index];
    const max = bounds.max[index];
    const center = bounds.center[index];
    const origin = tickOrigin(bounds, edge.axis, originMode);
    result.edgeIds.push(edge.id);

    if (showTicks) {
      // The default scale stays frame-centred. World mode aligns major steps
      // to SI zero so the displayed world coordinates remain a clean scale.
      const labelledTicks = new Set<number>();
      for (const value of centeredTicksBetween({
        max,
        min,
        origin,
        step: minorStep,
      })) {
        const major = isOnMajorStep(value - origin, step);
        const start = edge.at(value);
        const end = offsetPoint(start, edge.outward, major ? majorLength : minorLength);
        if (
          (major ? result.majorTickLines : result.minorTickLines).length / 6 <
          (major ? MAJOR_SEGMENT_CAP : MINOR_SEGMENT_CAP)
        ) {
          pushSegment(major ? result.majorTickLines : result.minorTickLines, start, end);
        }
        const tickIndex = Math.round((value - origin) / step);
        if (major && tickLabelCount < LABEL_CAP && !labelledTicks.has(tickIndex)) {
          labelledTicks.add(tickIndex);
          tickLabelCount += 1;
          result.labels.push({
            axis: edge.axis,
            key: `tick:${edge.axis}:${tickIndex}`,
            kind: "tick",
            outward: edge.outward,
            pixelOffset: TICK_LABEL_GAP_PX,
            position: end,
            text: formatDimensionFrameTickValue(
              originMode === "world" ? value : value - center,
              unit,
            ),
            tickIndex,
          });
        }
      }
      result.labels.push({
        axis: edge.axis,
        key: `title:${edge.axis}`,
        kind: "title",
        outward: edge.outward,
        pixelOffset: TITLE_LABEL_GAP_PX,
        position: offsetPoint(edge.at(center), edge.outward, majorLength),
        text: edge.axis,
        unitLabel: unit.label,
      });
    }

    if (showExtents) {
      appendExtent(result, edge, { annotation, center, max, maxSpan, min, unit });
    }
  }
  return result;
}

function appendExtent(
  result: EdgeAnnotations,
  edge: DimensionFrameEdge,
  {
    annotation,
    center,
    max,
    maxSpan,
    min,
    unit,
  }: {
    annotation: DimensionFrameAnnotation;
    center: number;
    max: number;
    maxSpan: number;
    min: number;
    unit: DimensionFrameUnit;
  },
): void {
  const offset = maxSpan * EXTENT_OFFSET_FRACTION[annotation];
  const overshoot = maxSpan * 0.012;
  const gap = maxSpan * 0.008;
  const arrowLength = Math.min(maxSpan * 0.03, (max - min) / 4);
  const arrowWidth = arrowLength * 0.35;
  const start = edge.at(min);
  const end = edge.at(max);
  const lineStart = offsetPoint(start, edge.outward, offset);
  const lineEnd = offsetPoint(end, edge.outward, offset);
  const along = AXIS_UNIT[edge.axis];

  // Witness lines, the dimension line, then an open arrowhead at each end.
  pushSegment(
    result.extentLines,
    offsetPoint(start, edge.outward, gap),
    offsetPoint(start, edge.outward, offset + overshoot),
  );
  pushSegment(
    result.extentLines,
    offsetPoint(end, edge.outward, gap),
    offsetPoint(end, edge.outward, offset + overshoot),
  );
  pushSegment(result.extentLines, lineStart, lineEnd);
  for (const [tip, direction] of [
    [lineStart, 1],
    [lineEnd, -1],
  ] as const) {
    const base = offsetPoint(tip, along, arrowLength * direction);
    pushSegment(result.extentLines, tip, offsetPoint(base, edge.outward, arrowWidth));
    pushSegment(result.extentLines, tip, offsetPoint(base, edge.outward, -arrowWidth));
  }
  result.labels.push({
    axis: edge.axis,
    key: `extent:${edge.axis}`,
    kind: "extent",
    outward: edge.outward,
    pixelOffset: EXTENT_LABEL_GAP_PX,
    position: offsetPoint(edge.at(center), edge.outward, offset),
    text: formatDimensionFrameTickValue(max - min, unit),
    unitLabel: unit.label,
  });
}

function offsetPoint(
  point: readonly [number, number, number],
  direction: readonly [number, number, number],
  distance: number,
): [number, number, number] {
  return [
    point[0] + direction[0] * distance,
    point[1] + direction[1] * distance,
    point[2] + direction[2] * distance,
  ];
}

function tickOrigin(
  bounds: ResolvedBounds,
  axis: DimensionFrameAxis,
  originMode: DimensionFrameOriginMode,
): number {
  return originMode === "world" ? 0 : bounds.center[AXIS_INDEX[axis]];
}

function buildAxisLines(
  bounds: ResolvedBounds,
  orientation: DimensionFrameCameraOrientation,
): number[] {
  const lines: number[] = [];
  for (const edge of resolveDimensionFrameEdgesForOrientation(bounds, orientation)) {
    const index = AXIS_INDEX[edge.axis];
    pushSegment(lines, edge.at(bounds.min[index]), edge.at(bounds.max[index]));
  }
  return lines;
}

function subtract(
  left: readonly [number, number, number],
  right: readonly [number, number, number],
): [number, number, number] {
  return [left[0] - right[0], left[1] - right[1], left[2] - right[2]];
}

/** Camera right vector restricted to the floor plane (x, y). */
function screenRight(cameraState: Viewport3DCameraState): [number, number] {
  const forward = subtract(cameraState.target, cameraState.position);
  const up = cameraState.up;
  const rightX = forward[1] * up[2] - forward[2] * up[1];
  const rightY = forward[2] * up[0] - forward[0] * up[2];
  const length = Math.hypot(rightX, rightY);
  if (length < 1e-12) return [1, 0];
  return [rightX / length, rightY / length];
}

function emptyDimensionFrameModel(
  mode: DimensionFrameMode,
  unit: DimensionFrameUnit,
  annotation: DimensionFrameAnnotation,
  originMode: DimensionFrameOriginMode,
): DimensionFrameModel {
  return {
    annotation,
    axisLines: EMPTY_LINES,
    extent: [
      [0, 0, 0],
      [0, 0, 0],
    ],
    extentLines: EMPTY_LINES,
    labels: [],
    majorLines: EMPTY_LINES,
    majorTickLines: EMPTY_LINES,
    minorLines: EMPTY_LINES,
    minorTickLines: EMPTY_LINES,
    mode,
    originMode,
    planes: [],
    signature: `${mode}:${unit.id}:${annotation}:${originMode}`,
    unit,
  };
}

function resolveBounds(bounds: Viewport3DBounds | null): ResolvedBounds {
  const center = bounds?.center ?? [0, 0, 0];
  const size = bounds?.size ?? [FALLBACK_SIZE, FALLBACK_SIZE, FALLBACK_SIZE];
  const halfSize = size.map((value) => Math.max(value, 1e-18) / 2) as [
    number,
    number,
    number,
  ];
  return {
    center,
    max: [
      center[0] + halfSize[0],
      center[1] + halfSize[1],
      center[2] + halfSize[2],
    ],
    min: [
      center[0] - halfSize[0],
      center[1] - halfSize[1],
      center[2] - halfSize[2],
    ],
    size: [halfSize[0] * 2, halfSize[1] * 2, halfSize[2] * 2],
  };
}

function niceStep(value: number): number {
  const exponent = Math.floor(Math.log10(Math.max(value, 1e-18)));
  const base = 10 ** exponent;
  const normalized = value / base;
  if (normalized <= 1) return base;
  if (normalized <= 2) return 2 * base;
  if (normalized <= 5) return 5 * base;
  return 10 * base;
}

function ticksBetween(min: number, max: number, step: number): number[] {
  if (!Number.isFinite(step) || step <= 0) return [];
  const ticks: number[] = [];
  const epsilon = step * 1e-6;
  const start = Math.ceil((min - epsilon) / step) * step;
  for (let value = start; value <= max + epsilon; value += step) {
    ticks.push(Number(value.toPrecision(12)));
  }
  return ticks;
}

function centeredTicksBetween({
  max,
  min,
  origin,
  step,
}: {
  max: number;
  min: number;
  origin: number;
  step: number;
}): number[] {
  if (!Number.isFinite(step) || step <= 0) return [];
  const relativeTicks = ticksBetween(min - origin, max - origin, step);
  return relativeTicks.map((value) => Number((origin + value).toPrecision(12)));
}

function isOnMajorStep(value: number, majorStep: number): boolean {
  const nearest = Math.round(value / majorStep) * majorStep;
  return Math.abs(value - nearest) <= Math.max(Math.abs(majorStep) * 1e-6, 1e-18);
}

function pointOnPlane(
  plane: DimensionFramePlane,
  fixedIndex: 0 | 1 | 2,
  fixedValue: number,
  firstIndex: 0 | 1 | 2,
  firstValue: number,
  secondIndex: 0 | 1 | 2,
  secondValue: number,
): [number, number, number] {
  const point: [number, number, number] = [0, 0, 0];
  point[fixedIndex] = fixedValue;
  point[firstIndex] = firstValue;
  point[secondIndex] = secondValue;
  const remainingIndex = remainingAxisIndex(fixedIndex, firstIndex, secondIndex);
  if (remainingIndex !== null) {
    point[remainingIndex] =
      plane.fixedAxis === "x" || plane.fixedAxis === "y" || plane.fixedAxis === "z"
        ? fixedValue
        : 0;
  }
  return point;
}

function remainingAxisIndex(
  a: 0 | 1 | 2,
  b: 0 | 1 | 2,
  c: 0 | 1 | 2,
): 0 | 1 | 2 | null {
  for (const index of [0, 1, 2] as const) {
    if (index !== a && index !== b && index !== c) return index;
  }
  return null;
}

function pushSegment(
  buffer: number[],
  start: [number, number, number],
  end: [number, number, number],
): void {
  buffer.push(...start, ...end);
}

function unitForId(id: Exclude<DimensionFrameUnitMode, "auto">): DimensionFrameUnit {
  if (id === "nm") return { factor: 1e9, id, label: "nm" };
  if (id === "um") return { factor: 1e6, id, label: "\u00b5m" };
  if (id === "mm") return { factor: 1e3, id, label: "mm" };
  return { factor: 1, id: "m", label: "m" };
}
