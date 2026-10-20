"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect } from "react";

import { registerViewport3DCaptureSource } from "../viewport3dImageExport";

/** Registers the live scene resources used by transparent and annotation-free PNG captures. */
export function Viewport3DCaptureSource({ onFrameReady }: { onFrameReady?: () => void }) {
  const { camera, gl, scene } = useThree();

  useEffect(
    () => registerViewport3DCaptureSource(gl.domElement, { camera, renderer: gl, scene }),
    [camera, gl, scene],
  );
  // Capture after the base/composer pass (1) and annotation pass (2), independently
  // of resource ACKs: even an empty scene can be exported without a data revision.
  useFrame(() => onFrameReady?.(), 3);

  return null;
}
