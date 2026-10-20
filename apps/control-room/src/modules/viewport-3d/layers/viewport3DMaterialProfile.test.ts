import { describe, expect, it } from "vitest";

import { getViewport3DVisualProfile } from "../viewport3dVisualProfile";
import { resolveViewport3DMaterialProfile } from "./viewport3DMaterialProfile";

describe("viewport3D material profile", () => {
  it("keeps quantitative shade strength independent from visual quality", () => {
    const interactive = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive"),
    );
    const figure = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("figure"),
    );
    const capture = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("capture"),
    );

    expect(interactive.magneticSurface.shadeStrength).toBe(0);
    expect(figure.magneticSurface.shadeStrength).toBe(0);
    expect(capture.magneticSurface.shadeStrength).toBe(0);
    expect(figure.magneticSurface.toneMapped).toBe(false);
    expect(capture.magneticSurface.toneMapped).toBe(false);
  });

  it("keeps quantitative field colors unshaded in both geometry lighting modes", () => {
    const studio = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive"),
      { lightingMode: "studio" },
    );
    const flat = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("capture"),
      { lightingMode: "flat" },
    );

    expect(studio.magneticSurface.shadeStrength).toBe(0);
    expect(flat.magneticSurface.shadeStrength).toBe(0);
    expect(studio).not.toHaveProperty("fieldColorShading");
    expect(flat).not.toHaveProperty("fieldColorShading");
  });

  it("keeps lite materials un-tonemapped", () => {
    const profile = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive-lite"),
    );

    expect(profile.magneticSurface.toneMapped).toBe(false);
    expect(profile.primitivePreview.toneMapped).toBe(false);
  });

  it("keeps quantitative surfaces flat while enabling studio for uniform geometry", () => {
    const interactive = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive"),
    );

    expect(interactive.magneticSurface).toEqual({
      shadeStrength: 0,
      toneMapped: false,
    });
    expect(interactive.primitivePreview).toEqual({ toneMapped: false });
    expect(interactive.uniformGeometry.lit).toBe(true);
    expect(interactive.magneticSurface).not.toHaveProperty("metalness");
    expect(interactive.magneticSurface).not.toHaveProperty("roughness");
    expect(interactive.primitivePreview).not.toHaveProperty("emissiveIntensity");
  });

  it("keeps lighting mode independent from capture quality", () => {
    const interactive = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive"),
    );
    const figure = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("figure"),
    );

    expect(figure.primitivePreview).toEqual(interactive.primitivePreview);
    expect(figure.uniformGeometry).toEqual(interactive.uniformGeometry);
  });

  it("supports flat uniform geometry without changing quantitative shading", () => {
    const flat = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive"),
      { lightingMode: "flat" },
    );

    expect(flat.uniformGeometry.lit).toBe(false);
    expect(flat.magneticSurface.shadeStrength).toBe(0);
  });

  it("maps visual profile edge opacity and boost into feature edge opacity", () => {
    const lite = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive-lite"),
    );
    const figure = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("figure"),
    );

    expect(lite.featureEdges.opacity).toBeCloseTo(0.255);
    expect(figure.featureEdges.opacity).toBeGreaterThan(
      lite.featureEdges.opacity,
    );
  });

  it("centralizes non-surface semantic layer material settings", () => {
    const interactive = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive"),
    );
    const figure = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("figure"),
    );

    expect(interactive.glyphs).toEqual({
      opacityScale: 0.92,
      toneMapped: false,
    });
    expect(interactive.grid).toMatchObject({
      depthWrite: false,
      opacity: 0.26,
      toneMapped: false,
    });
    expect(interactive.axes.opacity).toBe(0.6);
    expect(interactive.dimensionFrame).toMatchObject({
      labelOpacity: expect.any(Number),
      majorOpacity: expect.any(Number),
      minorOpacity: expect.any(Number),
      tickOpacity: expect.any(Number),
    });
    expect(interactive.dimensionFrame.minorOpacity).toBeGreaterThanOrEqual(0.12);
    expect(interactive.dimensionFrame.minorOpacity).toBeLessThanOrEqual(0.28);
    expect(interactive.dimensionFrame.majorOpacity).toBeGreaterThanOrEqual(0.24);
    expect(interactive.dimensionFrame.majorOpacity).toBeLessThanOrEqual(0.46);
    expect(interactive.dimensionFrame.labelOpacity).toBeGreaterThanOrEqual(0.72);
    expect(interactive.dimensionFrame.labelOpacity).toBeLessThanOrEqual(1);
    expect(figure.dimensionFrame.majorOpacity).toBe(
      interactive.dimensionFrame.majorOpacity,
    );
    expect(figure.selectionShell.opacity).toBe(interactive.selectionShell.opacity);
  });

  it("keeps render pass policy out of material appearance profiles", () => {
    const profile = resolveViewport3DMaterialProfile(
      getViewport3DVisualProfile("interactive"),
    );

    expect(profile.magneticSurface).not.toHaveProperty("polygonOffset");
    expect(profile.airSurface).not.toHaveProperty("polygonOffset");
    expect(profile.primitivePreview).not.toHaveProperty("polygonOffset");
  });
});
