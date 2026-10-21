import { BoxGeometry, Mesh, MeshBasicMaterial, Raycaster, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import {
  createViewport3DHudRaycaster,
  enableViewport3DHudRaycasting,
  VIEWPORT_3D_HUD_LAYER,
} from "./viewport3dHudLayer";

describe("viewport HUD raycasting", () => {
  it("hits the rendered HUD layer without accepting scientific scene objects", () => {
    const geometry = new BoxGeometry(1, 1, 1);
    const material = new MeshBasicMaterial();
    const mesh = new Mesh(geometry, material);
    const raycaster = createViewport3DHudRaycaster();
    raycaster.set(new Vector3(0, 0, 2), new Vector3(0, 0, -1));
    mesh.updateMatrixWorld(true);
    try {
      expect(raycaster.intersectObject(mesh)).toHaveLength(0);
      mesh.layers.set(VIEWPORT_3D_HUD_LAYER);
      expect(raycaster.intersectObject(mesh).length).toBeGreaterThan(0);
    } finally {
      geometry.dispose();
      material.dispose();
    }
  });

  it("enables HUD pointer events while preserving scene and custom layers", () => {
    const raycaster = new Raycaster();
    raycaster.layers.enable(5);
    const originalMask = raycaster.layers.mask;
    const release = enableViewport3DHudRaycasting(raycaster);
    expect(raycaster.layers.isEnabled(0)).toBe(true);
    expect(raycaster.layers.isEnabled(5)).toBe(true);
    expect(raycaster.layers.isEnabled(VIEWPORT_3D_HUD_LAYER)).toBe(true);
    release();
    expect(raycaster.layers.mask).toBe(originalMask);
  });

  it("does not remove a HUD layer already enabled by its owner", () => {
    const raycaster = new Raycaster();
    raycaster.layers.enable(VIEWPORT_3D_HUD_LAYER);
    const originalMask = raycaster.layers.mask;
    const release = enableViewport3DHudRaycasting(raycaster);
    release();
    expect(raycaster.layers.mask).toBe(originalMask);
  });

  it("releases only its HUD bit and preserves later changes to other layers", () => {
    const raycaster = new Raycaster();
    const release = enableViewport3DHudRaycasting(raycaster);
    raycaster.layers.enable(7);
    release();
    expect(raycaster.layers.isEnabled(7)).toBe(true);
    expect(raycaster.layers.isEnabled(0)).toBe(true);
    expect(raycaster.layers.isEnabled(VIEWPORT_3D_HUD_LAYER)).toBe(false);
  });
});
