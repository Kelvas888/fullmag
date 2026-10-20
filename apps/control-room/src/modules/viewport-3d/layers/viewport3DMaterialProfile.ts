import type { MeshBasicMaterialParameters } from "three";

import {
  DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
  type Viewport3DAppearancePreferences,
} from "../viewport3dAppearancePreferences";
import type { Viewport3DVisualProfile } from "../viewport3dVisualProfile";

type Viewport3DMaterialAppearance = Pick<
  Viewport3DAppearancePreferences,
  "fieldShading" | "lightingIntensity" | "lightingMode"
>;

export interface Viewport3DMaterialProfile {
  fieldColorShading: boolean;
  airSurface: Pick<
    MeshBasicMaterialParameters,
    | "toneMapped"
  >;
  magneticSurface: Pick<
    MeshBasicMaterialParameters,
    | "toneMapped"
  > & {
    shadeStrength: number;
  };
  primitivePreview: Pick<
    MeshBasicMaterialParameters,
    | "toneMapped"
  >;
  uniformGeometry: {
    lit: boolean;
  };
  featureEdges: {
    opacity: number;
  };
  glyphs: {
    opacityScale: number;
    toneMapped: boolean;
  };
  grid: {
    depthTest: boolean;
    depthWrite: boolean;
    opacity: number;
    toneMapped: boolean;
  };
  axes: {
    depthTest: boolean;
    depthWrite: boolean;
    opacity: number;
    toneMapped: boolean;
  };
  dimensionFrame: {
    labelOpacity: number;
    majorOpacity: number;
    minorOpacity: number;
    tickOpacity: number;
  };
  selectionShell: {
    opacity: number;
  };
}

export function resolveViewport3DMaterialProfile(
  visualProfile: Viewport3DVisualProfile,
  appearance: Viewport3DMaterialAppearance =
    DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
): Viewport3DMaterialProfile {
  const figureBoost = visualProfile.lighting === "figure" ? 1 : 0;
  const fieldColorShading = appearance.fieldShading;
  const lightingIntensity = Number.isFinite(appearance.lightingIntensity)
    ? Math.min(2, Math.max(0, appearance.lightingIntensity))
    : 1;
  return {
    fieldColorShading,
    airSurface: {
      toneMapped: visualProfile.toneMapping !== "none",
    },
    magneticSurface: {
      // Quantitative colors stay unmodulated unless shape shading is explicitly
      // requested. Keep tone mapping out of data colors across quality profiles.
      shadeStrength: fieldColorShading ? 0.45 * lightingIntensity : 0,
      toneMapped: false,
    },
    primitivePreview: {
      toneMapped: visualProfile.toneMapping !== "none",
    },
    uniformGeometry: {
      lit: appearance.lightingMode === "studio",
    },
    featureEdges: {
      opacity: Math.max(
        0,
        Math.min(1, visualProfile.edgeOpacity * visualProfile.edgeBoost),
      ),
    },
    glyphs: {
      opacityScale: visualProfile.lighting === "figure" ? 1 : 0.92,
      toneMapped: false,
    },
    grid: {
      depthTest: true,
      depthWrite: false,
      opacity: visualProfile.lighting === "minimal" ? 0.26 : 0.34,
      toneMapped: false,
    },
    axes: {
      depthTest: true,
      depthWrite: false,
      opacity: visualProfile.lighting === "minimal" ? 0.6 : 0.75,
      toneMapped: false,
    },
    dimensionFrame: {
      labelOpacity: 0.95,
      majorOpacity: visualProfile.lighting === "minimal" ? 0.34 : 0.38 + figureBoost * 0.06,
      minorOpacity: visualProfile.lighting === "minimal" ? 0.14 : 0.22 + figureBoost * 0.04,
      tickOpacity: visualProfile.lighting === "minimal" ? 0.68 : 0.7 + figureBoost * 0.08,
    },
    selectionShell: {
      opacity: visualProfile.lighting === "figure" ? 0.82 : 0.72,
    },
  };
}
