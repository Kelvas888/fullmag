"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  DirectionalLight,
  Quaternion,
  Vector3,
  type ColorRepresentation,
} from "three";

import {
  DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
  type Viewport3DAppearancePreferences,
} from "../viewport3dAppearancePreferences";
import {
  getViewport3DVisualProfile,
  type Viewport3DVisualProfile,
  type Viewport3DVisualProfileId,
} from "../viewport3dVisualProfile";

export type Viewport3DLightingAppearance = Pick<
  Viewport3DAppearancePreferences,
  | "lightingAzimuth"
  | "lightingElevation"
  | "lightingIntensity"
  | "lightingMode"
  | "lightingSpace"
>;

export interface Viewport3DLightingRigModel {
  ambient: {
    color: ColorRepresentation;
    intensity: number;
  };
  directional: Array<{
    color: ColorRepresentation;
    intensity: number;
    key: "fill" | "key";
    position: [number, number, number];
  }>;
  hemisphere: {
    args: [ColorRepresentation, ColorRepresentation, number];
  } | null;
}

const LIGHT_DISTANCE = 10;
const KEY_INTENSITY = 0.82;
const FILL_INTENSITY = 0.28;
const STUDIO_AMBIENT_INTENSITY = 0.24;

function clampLightingIntensity(value: number): number {
  return Number.isFinite(value) ? Math.min(2, Math.max(0, value)) : 1;
}

function directionFromAngles(azimuthDegrees: number, elevationDegrees: number) {
  const azimuth = (azimuthDegrees * Math.PI) / 180;
  const elevation = (elevationDegrees * Math.PI) / 180;
  const cosElevation = Math.cos(elevation);
  return new Vector3(
    Math.sin(azimuth) * cosElevation,
    Math.sin(elevation),
    Math.cos(azimuth) * cosElevation,
  ).normalize();
}

function lightPosition(direction: Vector3): [number, number, number] {
  return [
    direction.x * LIGHT_DISTANCE,
    direction.y * LIGHT_DISTANCE,
    direction.z * LIGHT_DISTANCE,
  ];
}

export function resolveViewport3DLightingRig(
  profile: Viewport3DVisualProfile,
  appearance: Viewport3DLightingAppearance =
    DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
): Viewport3DLightingRigModel {
  const studioEnabled = appearance.lightingMode === "studio";
  const rigEnabled = studioEnabled;
  const intensity = clampLightingIntensity(appearance.lightingIntensity);
  const keyDirection = directionFromAngles(
    appearance.lightingAzimuth,
    appearance.lightingElevation,
  );
  const fillDirection = directionFromAngles(
    appearance.lightingAzimuth + 100,
    Math.max(-10, appearance.lightingElevation - 18),
  );

  return {
    ambient: {
      color: 0xffffff,
      intensity: rigEnabled
        ? STUDIO_AMBIENT_INTENSITY * intensity
        : profile.lighting === "minimal"
          ? 0.6
          : 0.72,
    },
    directional: rigEnabled
      ? [
          {
            key: "key",
            color: 0xffffff,
            intensity: KEY_INTENSITY * intensity,
            position: lightPosition(keyDirection),
          },
          {
            key: "fill",
            color: 0xffffff,
            intensity: FILL_INTENSITY * intensity,
            position: lightPosition(fillDirection),
          },
        ]
      : [],
    hemisphere: null,
  };
}

export function Viewport3DLightingRig({
  appearance = DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
  profileId,
}: {
  appearance?: Viewport3DLightingAppearance;
  profileId: Viewport3DVisualProfileId;
}) {
  const profile = getViewport3DVisualProfile(profileId);
  const rig = resolveViewport3DLightingRig(profile, appearance);
  const keyLightRef = useRef<DirectionalLight>(null);
  const fillLightRef = useRef<DirectionalLight>(null);
  const cameraQuaternion = useMemo(() => new Quaternion(), []);
  const keyLocalDirection = useMemo(
    () => directionFromAngles(appearance.lightingAzimuth, appearance.lightingElevation),
    [appearance.lightingAzimuth, appearance.lightingElevation],
  );
  const fillLocalDirection = useMemo(
    () =>
      directionFromAngles(
        appearance.lightingAzimuth + 100,
        Math.max(-10, appearance.lightingElevation - 18),
      ),
    [appearance.lightingAzimuth, appearance.lightingElevation],
  );
  const worldPosition = useMemo(() => new Vector3(), []);

  useFrame(({ camera }) => {
    camera.getWorldQuaternion(cameraQuaternion);
    if (keyLightRef.current) {
      worldPosition
        .copy(keyLocalDirection)
        .multiplyScalar(LIGHT_DISTANCE);
      if (appearance.lightingSpace === "camera") worldPosition.applyQuaternion(cameraQuaternion);
      keyLightRef.current.position.copy(worldPosition);
    }
    if (fillLightRef.current) {
      worldPosition
        .copy(fillLocalDirection)
        .multiplyScalar(LIGHT_DISTANCE);
      if (appearance.lightingSpace === "camera") worldPosition.applyQuaternion(cameraQuaternion);
      fillLightRef.current.position.copy(worldPosition);
    }
  });

  return (
    <>
      <ambientLight color={rig.ambient.color} intensity={rig.ambient.intensity} />
      {rig.directional.map((light) => (
        <directionalLight
          color={light.color}
          intensity={light.intensity}
          key={light.key}
          position={light.position}
          ref={light.key === "key" ? keyLightRef : fillLightRef}
        />
      ))}
      {rig.hemisphere ? <hemisphereLight args={rig.hemisphere.args} /> : null}
    </>
  );
}
