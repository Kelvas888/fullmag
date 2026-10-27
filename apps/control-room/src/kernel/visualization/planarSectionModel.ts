import type {
  DomainMetaResource,
  VisualizationStateResource,
} from "@/kernel/api/apiTypes";

export type PlanarSectionPlane = "xy" | "xz" | "yz";
export type PlanarSectionAxis = "x" | "y" | "z";
type DefaultSlice = NonNullable<VisualizationStateResource["planar"]>["default_slice"];
type DefaultOperator = DefaultSlice["operator"];

const AXIS_INDEX = { x: 0, y: 1, z: 2 } as const;
const PLANE_AXES: Record<PlanarSectionPlane, {
  normal: PlanarSectionAxis;
  u: PlanarSectionAxis;
  v: PlanarSectionAxis;
}> = {
  xy: { normal: "z", u: "x", v: "y" },
  xz: { normal: "y", u: "x", v: "z" },
  yz: { normal: "x", u: "y", v: "z" },
};

/** Raster limits accepted by the planar data-plane query. */
export const PLANAR_MIN_RESOLUTION = 16;
export const PLANAR_MAX_RESOLUTION = 2048;

/**
 * Factor applied to the domain extent for the "average over the full
 * thickness" slab. The default slice centre may sit anywhere inside the
 * domain (FDM snaps it to a cell centre), so twice the extent always covers
 * the whole domain; empty volume does not enter the occupied-measure mean.
 */
const FULL_THICKNESS_SLAB_FACTOR = 2;

export interface PlanarSectionGeometry {
  plane: PlanarSectionPlane;
  normal: PlanarSectionAxis;
  u: PlanarSectionAxis;
  v: PlanarSectionAxis;
  normalMin: number;
  normalMax: number;
  normalExtent: number;
  /** FDM cell layers along the normal; null for unstructured domains. */
  layerCount: number | null;
  layerSpacing: number | null;
  /** Native FDM cell counts along u and v; null for unstructured domains. */
  nativeResolution: readonly [number, number] | null;
}

export function planarSectionAxes(plane: PlanarSectionPlane) {
  return PLANE_AXES[plane];
}

function positiveInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0
    ? value
    : null;
}

export function resolvePlanarSectionGeometry(
  domain: DomainMetaResource | null | undefined,
  plane: PlanarSectionPlane,
): PlanarSectionGeometry | null {
  if (!domain) return null;
  const { min, max } = domain.bounds;
  if (min.length !== 3 || max.length !== 3) return null;
  const axes = PLANE_AXES[plane];
  const n = AXIS_INDEX[axes.normal];
  const normalMin = min[n];
  const normalMax = max[n];
  if (!Number.isFinite(normalMin) || !Number.isFinite(normalMax) || normalMax <= normalMin) {
    return null;
  }
  const fdm = typeof domain.discretization === "string" &&
    domain.discretization.trim().toLowerCase() === "fdm";
  const grid = fdm ? domain.grid : null;
  const shape = grid?.shape ?? [];
  const spacing = grid?.spacing ?? [];
  const layerCount = grid ? positiveInteger(shape[n]) : null;
  const layerSpacing =
    layerCount !== null && Number.isFinite(spacing[n]) && spacing[n] > 0 ? spacing[n] : null;
  const nativeU = grid ? positiveInteger(shape[AXIS_INDEX[axes.u]]) : null;
  const nativeV = grid ? positiveInteger(shape[AXIS_INDEX[axes.v]]) : null;
  return {
    plane,
    ...axes,
    normalMin,
    normalMax,
    normalExtent: normalMax - normalMin,
    layerCount: layerSpacing === null ? null : layerCount,
    layerSpacing,
    nativeResolution:
      nativeU !== null && nativeV !== null ? [nativeU, nativeV] : null,
  };
}

function clampFraction(fraction: number): number {
  return Number.isFinite(fraction) ? Math.min(1, Math.max(0, fraction)) : 0.5;
}

/** Mirrors the backend FDM snap: `index = ceil(f * N) - 1`, clamped. */
export function layerIndexFromFraction(fraction: number, layerCount: number): number {
  const scaled = clampFraction(fraction) * layerCount;
  const index = scaled <= 0 ? 0 : Math.ceil(scaled) - 1;
  return Math.min(Math.max(index, 0), layerCount - 1);
}

/** Fraction at the centre of a layer; it snaps back to exactly that layer. */
export function fractionFromLayerIndex(index: number, layerCount: number): number {
  const clamped = Math.min(Math.max(Math.round(index), 0), layerCount - 1);
  return (clamped + 0.5) / layerCount;
}

/** Normal coordinate actually sampled by the backend for this fraction. */
export function resolvedSectionCoordinate(
  geometry: PlanarSectionGeometry,
  fraction: number,
): number {
  if (geometry.layerCount !== null && geometry.layerSpacing !== null) {
    const index = layerIndexFromFraction(fraction, geometry.layerCount);
    return geometry.normalMin + (index + 0.5) * geometry.layerSpacing;
  }
  return geometry.normalMin + clampFraction(fraction) * geometry.normalExtent;
}

export function fullThicknessSlabOperator(
  geometry: PlanarSectionGeometry,
): Extract<DefaultOperator, { kind: "slab_average" }> {
  return {
    kind: "slab_average",
    thickness_m: FULL_THICKNESS_SLAB_FACTOR * geometry.normalExtent,
  };
}

/** True when the slab covers the whole domain along the normal. */
export function isFullThicknessOperator(
  operator: DefaultOperator,
  geometry: PlanarSectionGeometry | null,
): boolean {
  if (operator.kind !== "slab_average" || !geometry) return false;
  return operator.thickness_m >= FULL_THICKNESS_SLAB_FACTOR * geometry.normalExtent * (1 - 1e-9);
}

export type PlanarSectionReduction = "single" | "average";

export function sectionReduction(
  operator: DefaultOperator,
  geometry: PlanarSectionGeometry | null,
): PlanarSectionReduction {
  return isFullThicknessOperator(operator, geometry) ? "average" : "single";
}

function clampResolution(value: number): number {
  return Math.min(PLANAR_MAX_RESOLUTION, Math.max(PLANAR_MIN_RESOLUTION, Math.round(value)));
}

/** Native FDM raster (one pixel per cell) within the accepted query limits. */
export function nativePlanarResolution(
  geometry: PlanarSectionGeometry | null,
): readonly [number, number] | null {
  const native = geometry?.nativeResolution;
  return native ? [clampResolution(native[0]), clampResolution(native[1])] : null;
}

export interface PlanarResolutionPreset {
  label: string;
  width: number;
  height: number;
}

/**
 * FDM raster presets: the native grid and its integer reductions. When the
 * factor divides the cell counts every pixel covers whole cells, so the area
 * average is exact; sizes are clamped to the accepted query limits.
 */
export function planarGridResolutionPresets(
  geometry: PlanarSectionGeometry | null,
): PlanarResolutionPreset[] {
  const native = geometry?.nativeResolution;
  if (!native) return [];
  const presets: PlanarResolutionPreset[] = [];
  for (const factor of [1, 2, 4, 8, 16, 32]) {
    if (factor > 1 && native[0] / factor < PLANAR_MIN_RESOLUTION) break;
    const width = clampResolution(native[0] / factor);
    const height = clampResolution(native[1] / factor);
    if (presets.some((preset) => preset.width === width && preset.height === height)) continue;
    presets.push({
      label: factor === 1 ? `Native grid (${width} × ${height})` : `1/${factor} grid (${width} × ${height})`,
      width,
      height,
    });
  }
  return presets;
}

export function formatSectionLength(meters: number): string {
  if (!Number.isFinite(meters)) return "—";
  const nm = meters * 1e9;
  const abs = Math.abs(nm);
  if (abs >= 1000) return `${(nm / 1000).toFixed(abs >= 10000 ? 1 : 2)} µm`;
  if (abs >= 100) return `${nm.toFixed(0)} nm`;
  if (abs >= 10) return `${nm.toFixed(1)} nm`;
  return `${nm.toFixed(2)} nm`;
}

/** Fraction step used for continuous (unstructured) sections: 1 % of the extent. */
const CONTINUOUS_SECTION_STEP = 0.01;

/**
 * Move the default slice by `delta` layers (FDM) or `delta` navigation steps
 * (continuous sections). The result always lands on a layer centre when the
 * section has discrete layers, so it snaps back to exactly that layer.
 */
export function stepSectionFraction(
  fraction: number,
  geometry: PlanarSectionGeometry | null,
  delta: number,
): number {
  if (geometry?.layerCount != null) {
    const index = layerIndexFromFraction(fraction, geometry.layerCount);
    return fractionFromLayerIndex(index + Math.round(delta), geometry.layerCount);
  }
  return clampFraction(clampFraction(fraction) + delta * CONTINUOUS_SECTION_STEP);
}
