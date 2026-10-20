"use client";

import { Bloom, EffectComposer, N8AO } from "@react-three/postprocessing";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect } from "react";

import { viewport3DPostProcessingEnabledFromBrowserConfig } from "@/kernel/browserFullmagConfig";
import { useViewport3DCommandState, viewport3dStore } from "../viewport3dStore";
import { useBatchedInvalidate } from "../viewport3dBatchedInvalidate";
import { enableViewport3DHudRaycasting, VIEWPORT_3D_HUD_LAYER } from "../viewport3dHudLayer";

/** Owns render ordering even when effects are off. Never schedules continuous frames. */
export function PostProcessingLayer({ quantitativeDataVisible = false, sceneSpan = 1 }: {
  quantitativeDataVisible?: boolean;
  sceneSpan?: number;
}) {
  const { appearance, widgets, visualProfileId } = useViewport3DCommandState();
  const invalidate = useBatchedInvalidate("material-style");
  const raycaster = useThree((state) => state.raycaster);
  const getThree = useThree((state) => state.get);
  const available = viewport3DPostProcessingEnabledFromBrowserConfig();
  const enabled = available && !quantitativeDataVisible;
  const ao = enabled && widgets.effectAmbientOcclusion;
  const bloom = enabled && widgets.effectBloom;
  const hasEffects = ao || bloom;
  useEffect(() => {
    const { gl } = getThree();
    const previous = gl.info.autoReset;
    gl.info.autoReset = false;
    return () => { gl.info.autoReset = previous; };
  }, [getThree]);
  useEffect(() => {
    return enableViewport3DHudRaycasting(raycaster);
  }, [raycaster]);
  useEffect(() => {
    viewport3dStore.setPostProcessingDataProtection(quantitativeDataVisible);
    viewport3dStore.setPostProcessingAvailable(available);
    return () => viewport3dStore.setPostProcessingDataProtection(false);
  }, [available, quantitativeDataVisible]);
  useEffect(() => { invalidate(); }, [invalidate, ao, bloom, appearance.aoRadius, appearance.aoIntensity]);

  // A positive priority owns the base draw; the composer owns it when enabled.
  // Count the whole scene and HUD frame rather than only the final overlay draw.
  useFrame(({ gl }) => gl.info.reset(), 0.5);
  useFrame(({ gl, scene, camera }) => {
    if (!hasEffects) gl.render(scene, camera);
  }, 1);
  useFrame(({ gl, scene, camera }) => {
    if (visualProfileId === "capture" && !appearance.exportAnnotations) return;
    const background = scene.background;
    const mask = camera.layers.mask;
    const autoClear = gl.autoClear;
    try {
      scene.background = null;
      camera.layers.set(VIEWPORT_3D_HUD_LAYER);
      gl.autoClear = false;
      gl.clearDepth();
      gl.render(scene, camera);
    } finally {
      scene.background = background;
      camera.layers.mask = mask;
      gl.autoClear = autoClear;
    }
  }, 2);

  if (!hasEffects) return null;
  return (
    <EffectComposer renderPriority={1} multisampling={widgets.effectAntialias ? 4 : 0}>
      <>
        {ao ? <N8AO aoRadius={Math.max(1e-12, Math.abs(sceneSpan)) * appearance.aoRadius} intensity={appearance.aoIntensity} halfRes /> : null}
        {bloom ? <Bloom luminanceThreshold={0.8} luminanceSmoothing={0.1} intensity={0.5} /> : null}
      </>
    </EffectComposer>
  );
}
