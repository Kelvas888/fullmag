"use client";

import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import { Color, DataTexture, LinearFilter, RGBAFormat, SRGBColorSpace } from "three";

import type { Viewport3DResourceTracker } from "../viewport3dDiagnostics";
import type { Viewport3DColors } from "../viewport3dTypes";
import { useBatchedInvalidate } from "../viewport3dBatchedInvalidate";

/** Rows run bottom to top; stored bytes are sRGB, interpolation is prepared in linear light. */
export function createViewportBackgroundTexture(colors: Viewport3DColors, strength: number): DataTexture {
  const height = 256;
  const pixels = new Uint8Array(height * 2 * 4);
  const amount = Math.min(1, Math.max(0, Number.isFinite(strength) ? strength : 0));
  const base = new Color(colors.background);
  const top = base.clone().lerp(new Color(colors.backgroundTop ?? colors.background), amount);
  const bottom = base.clone().lerp(new Color(colors.backgroundBottom ?? colors.background), amount);
  const sample = new Color();
  for (let row = 0; row < height; row += 1) {
    sample.copy(bottom).lerp(top, row / (height - 1)).convertLinearToSRGB();
    for (let column = 0; column < 2; column += 1) {
      const offset = (row * 2 + column) * 4;
      pixels[offset] = Math.round(sample.r * 255);
      pixels[offset + 1] = Math.round(sample.g * 255);
      pixels[offset + 2] = Math.round(sample.b * 255);
      pixels[offset + 3] = 255;
    }
  }
  const texture = new DataTexture(pixels, 2, height, RGBAFormat);
  texture.colorSpace = SRGBColorSpace;
  texture.minFilter = LinearFilter;
  texture.magFilter = LinearFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

export function Viewport3DBackground({ colors, mode, strength, tracker }: {
  colors: Viewport3DColors;
  mode: "solid" | "gradient";
  strength: number;
  tracker: Viewport3DResourceTracker;
}) {
  const getThree = useThree((state) => state.get);
  const invalidate = useBatchedInvalidate("material-style");
  const background = useMemo(() => mode === "gradient"
    ? createViewportBackgroundTexture(colors, strength)
    : new Color(colors.background), [colors, mode, strength]);
  useEffect(() => {
    const scene = getThree().scene;
    const previous = scene.background;
    if (background instanceof DataTexture) tracker.track("texture", background);
    scene.background = background;
    tracker.recordDirtyFrame("material-style");
    invalidate();
    return () => {
      if (scene.background === background) scene.background = previous;
      if (background instanceof DataTexture) tracker.release("texture", background);
      invalidate();
    };
  }, [background, getThree, invalidate, tracker]);
  return null;
}
