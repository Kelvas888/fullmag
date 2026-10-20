"use client";

import { useFrame } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState, memo } from "react";
import {
  BufferAttribute,
  BufferGeometry,
  LessEqualDepth,
  Vector3,
  type Camera,
  type Sprite,
} from "three";

import type { Viewport3DResourceTracker } from "../viewport3dDiagnostics";
import { useBatchedInvalidate } from "../viewport3dBatchedInvalidate";
import type { Viewport3DBounds } from "../viewport3dRenderModel";
import type {
  Viewport3DCameraProjection,
  Viewport3DCameraState,
} from "../viewport3dStore";
import type { Viewport3DColors } from "../viewport3dTypes";
import { VIEWPORT_3D_HUD_LAYER } from "../viewport3dHudLayer";
import { hudAxisColor, resolveHudColors } from "../orientation/hudColors";
import {
  useHudTextTexture,
  type HudTextRun,
  type HudTextStyle,
} from "../orientation/hudText";
import {
  dimensionFrameBoundsFromProjectedCorners,
  resolveDimensionFrameLabelVisibility,
  type DimensionFrameLabelCandidate,
  type DimensionFramePixelRect,
  type DimensionFrameProjectedPoint,
} from "./dimensionFrameLabelLayout";
import {
  buildDimensionFrameModel,
  type DimensionFrameAnnotation,
  type DimensionFrameAxis,
  type DimensionFrameCameraOrientation,
  type DimensionFrameDensity,
  type DimensionFrameLabel,
  type DimensionFrameMode,
  type DimensionFrameModel,
  type DimensionFrameOriginMode,
  type DimensionFrameUnitMode,
  resolveDimensionFrameOrientation,
  resolveDimensionFrameOrientationWithHysteresis,
} from "./dimensionFrameModel";
import type { Viewport3DMaterialProfile } from "./viewport3DMaterialProfile";

interface DimensionFrameLayerProps {
  annotation?: DimensionFrameAnnotation;
  bounds: Viewport3DBounds | null;
  cameraProjection: Viewport3DCameraProjection;
  cameraState: Viewport3DCameraState;
  colors: Viewport3DColors;
  density: DimensionFrameDensity;
  gridOpacity?: number;
  labelsVisible: boolean;
  majorLinesVisible: boolean;
  materialProfile: Viewport3DMaterialProfile;
  mode: DimensionFrameMode;
  minorLinesVisible: boolean;
  originMode?: DimensionFrameOriginMode;
  reservedHudRegions?: readonly DimensionFramePixelRect[];
  tracker: Viewport3DResourceTracker;
  unitMode: DimensionFrameUnitMode;
}

export interface DimensionFrameLayerColors {
  axis: Record<DimensionFrameAxis, string>;
  axisLine: string;
  extent: string;
  grid: string;
  halo: string;
  label: string;
  tick: string;
}

type TickSpacingProbes = Partial<
  Record<DimensionFrameAxis, [DimensionFrameLabel, DimensionFrameLabel]>
>;

interface DimensionFrameCameraFrameState {
  cameraState: Viewport3DCameraState;
  forward: Vector3;
  position: Vector3;
  up: Vector3;
}

const DIMENSION_FRAME_RENDER_ORDER = 4;
const TICK_LABEL_FONT_PX = 11;
const TITLE_LABEL_FONT_PX = 12;
/** Minimum on-screen spacing between neighbouring tick numbers. */
const TICK_LABEL_MIN_SPACING_PX = 34;
/** Below this projected length the outward direction is seen end-on. */
const DEGENERATE_OUTWARD = 0.2;
const ANCHOR_THRESHOLD = 0.35;

function createDimensionFrameCameraFrameState(): DimensionFrameCameraFrameState {
  return {
    cameraState: {
      position: [0, 0, 0],
      target: [0, 0, 1],
      up: [0, 0, 1],
    },
    forward: new Vector3(),
    position: new Vector3(),
    up: new Vector3(),
  };
}

export const DimensionFrameLayer = memo(function DimensionFrameLayer({
  annotation = "ticks",
  bounds,
  cameraProjection,
  cameraState,
  colors,
  density,
  gridOpacity = 1,
  labelsVisible,
  majorLinesVisible,
  materialProfile,
  mode,
  minorLinesVisible,
  originMode = "frame-center",
  reservedHudRegions = [],
  tracker,
  unitMode,
}: DimensionFrameLayerProps) {
  const invalidate = useBatchedInvalidate("resize");
  const layerColors = useMemo(
    () => resolveDimensionFrameLayerColors(colors),
    [colors],
  );
  const [cameraOrientation, setCameraOrientation] = useState(() =>
    resolveDimensionFrameOrientation(bounds, cameraState),
  );
  const cameraOrientationRef = useRef<DimensionFrameCameraOrientation | null>(null);
  const cameraFrameStateRef = useRef<DimensionFrameCameraFrameState | null>(null);

  useFrame(({ camera }) => {
    if (mode === "off") return;
    const frameState =
      cameraFrameStateRef.current ?? createDimensionFrameCameraFrameState();
    cameraFrameStateRef.current = frameState;
    camera.updateWorldMatrix(true, false);
    camera.getWorldPosition(frameState.position);
    camera.getWorldDirection(frameState.forward);
    frameState.up.setFromMatrixColumn(camera.matrixWorld, 1).normalize();
    frameState.cameraState.position[0] = frameState.position.x;
    frameState.cameraState.position[1] = frameState.position.y;
    frameState.cameraState.position[2] = frameState.position.z;
    frameState.cameraState.target[0] = frameState.position.x + frameState.forward.x;
    frameState.cameraState.target[1] = frameState.position.y + frameState.forward.y;
    frameState.cameraState.target[2] = frameState.position.z + frameState.forward.z;
    frameState.cameraState.up[0] = frameState.up.x;
    frameState.cameraState.up[1] = frameState.up.y;
    frameState.cameraState.up[2] = frameState.up.z;

    const previous = cameraOrientationRef.current ?? cameraOrientation;
    const next = resolveDimensionFrameOrientationWithHysteresis(
      bounds,
      frameState.cameraState,
      previous,
    );
    if (!cameraOrientationRef.current) cameraOrientationRef.current = previous;
    if (!sameDimensionFrameOrientation(previous, next)) {
      cameraOrientationRef.current = next;
      setCameraOrientation(next);
      invalidate();
    }
  });

  const model = useMemo(
    () =>
      buildDimensionFrameModel({
        annotation,
        bounds,
        cameraOrientation,
        cameraProjection,
        density,
        labelsVisible,
        mode,
        originMode,
        unitMode,
      }),
    [
      annotation,
      bounds,
      cameraProjection,
      density,
      labelsVisible,
      mode,
      originMode,
      unitMode,
      cameraOrientation,
    ],
  );
  const axisGeometry = useTrackedLineGeometry(tracker, model.axisLines);
  const minorGeometry = useTrackedLineGeometry(
    tracker,
    minorLinesVisible ? model.minorLines : null,
  );
  const majorGeometry = useTrackedLineGeometry(
    tracker,
    majorLinesVisible ? model.majorLines : null,
  );
  const majorTickGeometry = useTrackedLineGeometry(tracker, model.majorTickLines);
  const minorTickGeometry = useTrackedLineGeometry(tracker, model.minorTickLines);
  const extentGeometry = useTrackedLineGeometry(tracker, model.extentLines);
  const resolvedGridOpacity = clampGridContrast(gridOpacity);

  useEffect(() => {
    tracker.recordDirtyFrame("dimension-frame");
    invalidate();
  }, [invalidate, model.signature, tracker]);

  if (mode === "off") {
    return null;
  }

  const frame = materialProfile.dimensionFrame;
  return (
    <group renderOrder={DIMENSION_FRAME_RENDER_ORDER}>
      <FrameLines
        color={layerColors.grid}
        geometry={minorGeometry}
        opacity={frame.minorOpacity * resolvedGridOpacity}
        renderOrder={DIMENSION_FRAME_RENDER_ORDER}
      />
      <FrameLines
        color={layerColors.grid}
        geometry={majorGeometry}
        opacity={frame.majorOpacity * resolvedGridOpacity}
        renderOrder={DIMENSION_FRAME_RENDER_ORDER + 1}
      />
      <FrameLines
        color={layerColors.tick}
        geometry={minorTickGeometry}
        opacity={frame.tickOpacity}
        renderOrder={DIMENSION_FRAME_RENDER_ORDER + 2}
        screenLengthPx={4}
      />
      <FrameLines
        color={layerColors.tick}
        geometry={majorTickGeometry}
        opacity={frame.labelOpacity}
        renderOrder={DIMENSION_FRAME_RENDER_ORDER + 2}
        screenLengthPx={7}
      />
      <FrameLines
        color={layerColors.extent}
        geometry={extentGeometry}
        opacity={frame.labelOpacity}
        renderOrder={DIMENSION_FRAME_RENDER_ORDER + 2}
      />
      {/* Later render order plus LEQUAL resolves exact edge ties without moving SI coordinates. */}
      <FrameLines
        color={layerColors.axisLine}
        geometry={axisGeometry}
        opacity={frame.labelOpacity}
        renderOrder={DIMENSION_FRAME_RENDER_ORDER + 3}
      />
      {model.labels.length > 0 ? (
        <DimensionFrameLabels
          colors={layerColors}
          extent={model.extent}
          labels={model.labels}
          opacity={frame.labelOpacity}
          reservedHudRegions={reservedHudRegions}
        />
      ) : null}
    </group>
  );
});

function FrameLines({
  color,
  geometry,
  opacity,
  renderOrder,
  screenLengthPx,
}: {
  color: string;
  geometry: BufferGeometry | null;
  opacity: number;
  renderOrder: number;
  screenLengthPx?: number;
}) {
  if (!geometry) return null;
  return (
    <lineSegments
      frustumCulled={screenLengthPx === undefined}
      geometry={geometry}
      renderOrder={renderOrder}
    >
      <lineBasicMaterial
        color={color}
        depthTest
        depthWrite={false}
        depthFunc={LessEqualDepth}
        opacity={opacity}
        toneMapped={false}
        transparent
        onBeforeCompile={(shader) => {
          // Bias only projected depth; measured coordinates and tick values stay unchanged.
          shader.vertexShader = shader.vertexShader.replace(
            "#include <project_vertex>",
            "#include <project_vertex>\ngl_Position.z -= 0.000002 * gl_Position.w;",
          );
        }}
        customProgramCacheKey={() => "dimension-frame-depth-bias-v1"}
      />
      {screenLengthPx === undefined ? null : (
        <ScreenBoundTickLengths geometry={geometry} pixelLength={screenLengthPx} />
      )}
    </lineSegments>
  );
}

/** Updates only tick endpoints, keeping their length stable in CSS pixels. */
function ScreenBoundTickLengths({
  geometry,
  pixelLength,
}: {
  geometry: BufferGeometry;
  pixelLength: number;
}) {
  const basePositions = useMemo(() => {
    const attribute = geometry.getAttribute("position");
    return new Float32Array(attribute.array as Float32Array);
  }, [geometry]);
  const frameStateRef = useRef<ScreenBoundTickFrameState | null>(null);

  useFrame(({ camera, size }) => {
    const frameState =
      frameStateRef.current ?? createScreenBoundTickFrameState();
    frameStateRef.current = frameState;
    camera.updateMatrixWorld();
    let changed =
      !frameState.hasPreviousCameraMatrices || frameState.lastBasePositions !== basePositions;
    frameState.lastBasePositions = basePositions;
    const cameraMatrix = camera.matrixWorld.elements;
    const projectionMatrix = camera.projectionMatrix.elements;
    for (let index = 0; index < 16; index += 1) {
      if (
        frameState.previousCameraMatrices[index] !== cameraMatrix[index] ||
        frameState.previousCameraMatrices[index + 16] !== projectionMatrix[index]
      ) {
        changed = true;
      }
      frameState.previousCameraMatrices[index] = cameraMatrix[index] ?? 0;
      frameState.previousCameraMatrices[index + 16] = projectionMatrix[index] ?? 0;
    }
    if (frameState.previousCameraMatrices[32] !== size.height) changed = true;
    frameState.previousCameraMatrices[32] = size.height;
    frameState.hasPreviousCameraMatrices = true;
    if (!changed || size.height <= 0) return;

    camera.getWorldDirection(frameState.forward);
    const positions = geometry.getAttribute("position");
    for (let vertex = 0; vertex + 1 < positions.count; vertex += 2) {
      const index = vertex * 3;
      const endIndex = (vertex + 1) * 3;
      const startX = basePositions[index] ?? 0;
      const startY = basePositions[index + 1] ?? 0;
      const startZ = basePositions[index + 2] ?? 0;
      frameState.start.set(startX, startY, startZ);
      frameState.direction
        .set(
          (basePositions[endIndex] ?? startX) - startX,
          (basePositions[endIndex + 1] ?? startY) - startY,
          (basePositions[endIndex + 2] ?? startZ) - startZ,
        )
        .normalize();
      const worldLength =
        worldPerPixelAt(camera, frameState.start, frameState.forward, size.height) * pixelLength;
      positions.setXYZ(
        vertex + 1,
        startX + frameState.direction.x * worldLength,
        startY + frameState.direction.y * worldLength,
        startZ + frameState.direction.z * worldLength,
      );
    }
    positions.needsUpdate = true;
  });

  return null;
}

interface ScreenBoundTickFrameState {
  direction: Vector3;
  forward: Vector3;
  hasPreviousCameraMatrices: boolean;
  lastBasePositions: Float32Array | null;
  previousCameraMatrices: Float64Array;
  start: Vector3;
}

function createScreenBoundTickFrameState(): ScreenBoundTickFrameState {
  return {
    direction: new Vector3(),
    forward: new Vector3(),
    hasPreviousCameraMatrices: false,
    lastBasePositions: null,
    previousCameraMatrices: new Float64Array(33),
    start: new Vector3(),
  };
}

function clampGridContrast(value: number): number {
  return Number.isFinite(value) ? Math.min(2, Math.max(0, value)) : 1;
}

function sameDimensionFrameOrientation(
  left: DimensionFrameCameraOrientation,
  right: DimensionFrameCameraOrientation,
): boolean {
  return (
    left.xFacing === right.xFacing &&
    left.yFacing === right.yFacing &&
    left.zCornerX === right.zCornerX &&
    left.zCornerY === right.zCornerY
  );
}

function useTrackedLineGeometry(
  tracker: Viewport3DResourceTracker,
  positions: Float32Array | null,
): BufferGeometry | null {
  const geometry = useMemo(
    () => (positions ? createDimensionFrameLineGeometry(positions) : null),
    [positions],
  );
  useEffect(() => {
    if (!geometry) return undefined;
    trackDimensionFrameGeometry(tracker, geometry);
    return () => releaseDimensionFrameGeometry(tracker, geometry);
  }, [geometry, tracker]);
  return geometry;
}

export function createDimensionFrameLineGeometry(
  positions: Float32Array,
): BufferGeometry | null {
  if (positions.length === 0) return null;
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  geometry.computeBoundingSphere();
  return geometry;
}

export function trackDimensionFrameGeometry(
  tracker: Viewport3DResourceTracker,
  geometry: BufferGeometry,
): BufferGeometry {
  return tracker.track("geometry", geometry);
}

export function releaseDimensionFrameGeometry(
  tracker: Viewport3DResourceTracker,
  geometry: BufferGeometry | null,
): void {
  tracker.release("geometry", geometry);
}

export function resolveDimensionFrameLayerColors(
  colors: Viewport3DColors,
): DimensionFrameLayerColors {
  const hud = resolveHudColors(colors);
  return {
    axis: {
      x: hudAxisColor(hud, "x"),
      y: hudAxisColor(hud, "y"),
      z: hudAxisColor(hud, "z"),
    },
    axisLine: hud.label,
    extent: hud.label,
    grid: hud.grid,
    halo: hud.halo,
    label: hud.label,
    tick: hud.tick,
  };
}

/** Text runs for one frame label: numbers, "x (nm)" titles and "Lx = 240 nm". */
export function dimensionFrameLabelRuns(
  label: DimensionFrameLabel,
  colors: DimensionFrameLayerColors,
): { runs: HudTextRun[]; style: HudTextStyle } {
  const axisColor = colors.axis[label.axis];
  if (label.kind === "tick") {
    return {
      runs: [{ color: colors.label, text: label.text, weight: 700 }],
      style: { font: "mono", fontPx: TICK_LABEL_FONT_PX, halo: colors.halo },
    };
  }
  if (label.kind === "title") {
    return {
      runs: [
        { color: axisColor, italic: true, size: 1.15, text: label.text, weight: 800 },
        { color: colors.label, text: ` (${label.unitLabel ?? ""})`, weight: 600 },
      ],
      style: { font: "ui", fontPx: TITLE_LABEL_FONT_PX, halo: colors.halo },
    };
  }
  return {
    runs: [
      { color: axisColor, italic: true, text: "L", weight: 800 },
      {
        color: axisColor,
        italic: true,
        shiftPx: 3,
        size: 0.72,
        text: label.axis,
        weight: 800,
      },
      {
        color: colors.label,
        text: ` = ${label.text} ${label.unitLabel ?? ""}`,
        weight: 700,
      },
    ],
    style: { font: "mono", fontPx: TICK_LABEL_FONT_PX, halo: colors.halo },
  };
}

interface LabelFrameState {
  compact: boolean;
  depthPoint: Vector3;
  frameCorners: Vector3[];
  forward: Vector3;
  projected: Vector3;
  projectedFrameCorners: DimensionFrameProjectedPoint[];
  thinning: Record<DimensionFrameAxis, number>;
  probeA: Vector3;
  probeB: Vector3;
  right: Vector3;
  up: Vector3;
  visibleKeys: Set<string>;
  world: Vector3;
}

function createLabelFrameState(): LabelFrameState {
  return {
    compact: false,
    depthPoint: new Vector3(),
    frameCorners: Array.from({ length: 8 }, () => new Vector3()),
    forward: new Vector3(),
    projected: new Vector3(),
    projectedFrameCorners: Array.from({ length: 8 }, () => ({ x: 0, y: 0, z: 2 })),
    thinning: { x: 1, y: 1, z: 1 },
    probeA: new Vector3(),
    probeB: new Vector3(),
    right: new Vector3(),
    up: new Vector3(),
    visibleKeys: new Set<string>(),
    world: new Vector3(),
  };
}

/**
 * Labels keep a constant pixel size and sit `pixelOffset` px outside the
 * frame. Placement is recomputed every rendered frame, so it follows the
 * camera during an orbit without rebuilding the model.
 */
function DimensionFrameLabels({
  colors,
  extent,
  labels,
  opacity,
  reservedHudRegions,
}: {
  colors: DimensionFrameLayerColors;
  extent: DimensionFrameModel["extent"];
  labels: DimensionFrameLabel[];
  opacity: number;
  reservedHudRegions: readonly DimensionFramePixelRect[];
}) {
  const spritesRef = useRef<Map<string, Sprite> | null>(null);
  const frameStateRef = useRef<LabelFrameState | null>(null);
  const spacingProbes = useMemo(() => tickSpacingProbes(labels), [labels]);
  const register = useCallback((key: string, sprite: Sprite | null) => {
    const sprites = spritesRef.current ?? new Map<string, Sprite>();
    spritesRef.current = sprites;
    if (sprite) {
      sprite.layers.set(VIEWPORT_3D_HUD_LAYER);
      sprites.set(key, sprite);
    } else {
      sprites.delete(key);
    }
  }, []);

  useFrame(({ camera, size }) => {
    const sprites = spritesRef.current;
    if (!sprites) return;
    const frameState = frameStateRef.current ?? createLabelFrameState();
    frameStateRef.current = frameState;
    const { depthPoint, forward, projected, right, up, world } = frameState;
    camera.updateMatrixWorld();
    right.setFromMatrixColumn(camera.matrixWorld, 0).normalize();
    up.setFromMatrixColumn(camera.matrixWorld, 1).normalize();
    forward.setFromMatrixColumn(camera.matrixWorld, 2).normalize().negate();
    const [min, max] = extent;
    for (let index = 0; index < frameState.frameCorners.length; index += 1) {
      const corner = frameState.frameCorners[index];
      const projectedCorner = frameState.projectedFrameCorners[index];
      if (!corner || !projectedCorner) continue;
      corner
        .set(
          index & 1 ? max[0] : min[0],
          index & 2 ? max[1] : min[1],
          index & 4 ? max[2] : min[2],
        )
        .project(camera);
      projectedCorner.x = corner.x;
      projectedCorner.y = corner.y;
      projectedCorner.z = corner.z;
    }
    const frameBounds = dimensionFrameBoundsFromProjectedCorners(
      frameState.projectedFrameCorners,
      size,
    );
    const frameSpan = frameBounds
      ? Math.max(
          frameBounds.right - frameBounds.left,
          frameBounds.bottom - frameBounds.top,
        )
      : 0;
    // The wider exit threshold keeps compact mode stable during slow orbits.
    frameState.compact = frameState.compact
      ? frameSpan < 96
      : frameSpan < 84;
    const thinning = resolveTickThinning(spacingProbes, camera, size, frameState);
    const candidates: DimensionFrameLabelCandidate[] = [];

    for (const label of labels) {
      const sprite = sprites.get(label.key);
      if (!sprite) continue;
      world.set(label.outward[0], label.outward[1], label.outward[2]);
      let dx = world.dot(right);
      let dy = world.dot(up);
      const length = Math.hypot(dx, dy);
      if (length < DEGENERATE_OUTWARD) {
        dx = 0;
        dy = -1;
      } else {
        dx /= length;
        dy /= length;
      }
      sprite.center.set(anchorFor(dx), anchorFor(dy));
      world.set(label.position[0], label.position[1], label.position[2]);
      const worldPerPixel = worldPerPixelAt(camera, world, forward, size.height);
      const offset = label.pixelOffset * worldPerPixel;
      sprite.position
        .copy(world)
        .addScaledVector(right, dx * offset)
        .addScaledVector(up, dy * offset);
      const pixelSize = sprite.userData.pixelSize as [number, number] | undefined;
      if (pixelSize) {
        sprite.scale.set(
          pixelSize[0] * worldPerPixel,
          pixelSize[1] * worldPerPixel,
          1,
        );
      }
      if (!pixelSize || size.width <= 0 || size.height <= 0) continue;

      projected.copy(sprite.position).project(camera);
      depthPoint.copy(sprite.position).sub(camera.position);
      const cameraDepth = depthPoint.dot(forward);
      if (
        cameraDepth <= 0 ||
        projected.z < -1 ||
        projected.z > 1 ||
        !Number.isFinite(projected.x) ||
        !Number.isFinite(projected.y)
      ) {
        continue;
      }
      const screenX = ((projected.x + 1) / 2) * size.width;
      const screenY = ((1 - projected.y) / 2) * size.height;
      const anchorX = anchorFor(dx);
      const anchorY = anchorFor(dy);
      const left = screenX - anchorX * pixelSize[0];
      const top = screenY - (1 - anchorY) * pixelSize[1];
      const bounds: DimensionFramePixelRect = {
        bottom: top + pixelSize[1],
        left,
        right: left + pixelSize[0],
        top,
      };
      candidates.push({
        axis: label.axis,
        bounds,
        key: label.key,
        kind: label.kind,
        tickIndex: label.tickIndex,
        tickStride: thinning[label.axis],
      });
    }

    const visibleKeys = resolveDimensionFrameLabelVisibility(
      candidates,
      size,
      frameState.visibleKeys,
      frameState.compact,
      reservedHudRegions,
    );
    for (const [key, sprite] of sprites) {
      // Sprite visibility is a Three.js scene mutation owned by this frame hook.
      // eslint-disable-next-line react-hooks/immutability -- imperative Three.js interop in useFrame
      sprite.visible = visibleKeys.has(key);
    }
    frameState.visibleKeys.clear();
    for (const key of visibleKeys) frameState.visibleKeys.add(key);
  });

  return (
    <>
      {labels.map((label) => (
        <DimensionFrameLabelSprite
          key={label.key}
          colors={colors}
          label={label}
          opacity={opacity}
          register={register}
        />
      ))}
    </>
  );
}

/** Sprite.center: text grows away from the frame along the outward direction. */
function anchorFor(component: number): number {
  if (component > ANCHOR_THRESHOLD) return 0;
  if (component < -ANCHOR_THRESHOLD) return 1;
  return 0.5;
}

function DimensionFrameLabelSprite({
  colors,
  label,
  opacity,
  register,
}: {
  colors: DimensionFrameLayerColors;
  label: DimensionFrameLabel;
  opacity: number;
  register: (key: string, sprite: Sprite | null) => void;
}) {
  const { runs, style } = useMemo(
    () => dimensionFrameLabelRuns(label, colors),
    [colors, label],
  );
  const { heightPx, texture, widthPx } = useHudTextTexture(runs, style);
  const key = label.key;
  const ref = useCallback(
    (sprite: Sprite | null) => register(key, sprite),
    [key, register],
  );
  return (
    <sprite
      ref={ref}
      position={label.position}
      renderOrder={DIMENSION_FRAME_RENDER_ORDER + 3}
      // The real size is applied per frame from the camera.
      scale={[1e-12, 1e-12, 1]}
      userData={{ pixelSize: [widthPx, heightPx] }}
    >
      <spriteMaterial
        depthTest={false}
        depthWrite={false}
        map={texture}
        opacity={opacity}
        toneMapped={false}
        transparent
      />
    </sprite>
  );
}

function tickSpacingProbes(labels: DimensionFrameLabel[]): TickSpacingProbes {
  const probes: TickSpacingProbes = {};
  const byAxis = new Map<DimensionFrameAxis, Map<number, DimensionFrameLabel>>();
  for (const label of labels) {
    if (label.kind !== "tick" || label.tickIndex === undefined) continue;
    const axisLabels = byAxis.get(label.axis) ?? new Map<number, DimensionFrameLabel>();
    axisLabels.set(label.tickIndex, label);
    byAxis.set(label.axis, axisLabels);
  }
  for (const [axis, axisLabels] of byAxis) {
    for (const [index, label] of axisLabels) {
      const next = axisLabels.get(index + 1);
      if (next) {
        probes[axis] = [label, next];
        break;
      }
    }
  }
  return probes;
}

/** Shows every 1st, 2nd or 5th number so neighbours stay legible. */
export function tickThinningForSpacing(spacingPx: number, previous?: number): number {
  if (previous === undefined) {
    if (spacingPx >= TICK_LABEL_MIN_SPACING_PX) return 1;
    if (spacingPx >= TICK_LABEL_MIN_SPACING_PX / 2) return 2;
    return 5;
  }
  if (previous === 1) {
    if (spacingPx < 15) return 5;
    return spacingPx < TICK_LABEL_MIN_SPACING_PX - 4 ? 2 : 1;
  }
  if (previous === 2) {
    if (spacingPx >= TICK_LABEL_MIN_SPACING_PX + 5) return 1;
    return spacingPx < 15 ? 5 : 2;
  }
  if (spacingPx >= TICK_LABEL_MIN_SPACING_PX + 5) return 1;
  return spacingPx >= TICK_LABEL_MIN_SPACING_PX / 2 + 3 ? 2 : 5;
}

const FRAME_AXES: readonly DimensionFrameAxis[] = ["x", "y", "z"];

function resolveTickThinning(
  probes: TickSpacingProbes,
  camera: Camera,
  size: { height: number; width: number },
  state: LabelFrameState,
): Record<DimensionFrameAxis, number> {
  const thinning = state.thinning;
  for (const axis of FRAME_AXES) {
    const probe = probes[axis];
    if (!probe) {
      thinning[axis] = 1;
      continue;
    }
    state.probeA.set(...probe[0].position).project(camera);
    state.probeB.set(...probe[1].position).project(camera);
    thinning[axis] = tickThinningForSpacing(
      Math.hypot(
        ((state.probeA.x - state.probeB.x) * size.width) / 2,
        ((state.probeA.y - state.probeB.y) * size.height) / 2,
      ),
      thinning[axis],
    );
  }
  return thinning;
}

function worldPerPixelAt(
  camera: Camera,
  point: Vector3,
  forward: Vector3,
  viewportHeight: number,
): number {
  const height = Math.max(viewportHeight, 1);
  if ("isOrthographicCamera" in camera && camera.isOrthographicCamera) {
    const orthographic = camera as unknown as {
      bottom: number;
      top: number;
      zoom: number;
    };
    return (
      Math.abs(orthographic.top - orthographic.bottom) /
      (orthographic.zoom || 1) /
      height
    );
  }
  const fov = Number((camera as { fov?: unknown }).fov ?? 42);
  const distance = Math.max(
    (point.x - camera.position.x) * forward.x +
      (point.y - camera.position.y) * forward.y +
      (point.z - camera.position.z) * forward.z,
    1e-12,
  );
  return (2 * Math.tan((fov * Math.PI) / 360) * distance) / height;
}
