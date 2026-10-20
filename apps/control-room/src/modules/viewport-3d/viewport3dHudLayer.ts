import { Raycaster } from "three";

/** One renderer draws the scientific scene first and annotations after effects. */
export const VIEWPORT_3D_HUD_LAYER = 31;

export function createViewport3DHudRaycaster(): Raycaster {
  const raycaster = new Raycaster();
  raycaster.layers.set(VIEWPORT_3D_HUD_LAYER);
  return raycaster;
}

/** The HUD owns only its extra event layer, never the scene raycaster's mask. */
export function enableViewport3DHudRaycasting(raycaster: Raycaster): () => void {
  const wasEnabled = raycaster.layers.isEnabled(VIEWPORT_3D_HUD_LAYER);
  raycaster.layers.enable(VIEWPORT_3D_HUD_LAYER);
  return () => {
    if (!wasEnabled) raycaster.layers.disable(VIEWPORT_3D_HUD_LAYER);
  };
}
