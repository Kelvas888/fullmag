import { describe, expect, it } from "vitest";

import {
  DEFAULT_VIEWPORT_3D_CAMERA_FOV_DEGREES,
  isViewport3DCameraFovDegreesValid,
  resolveViewport3DCameraFovDegrees,
} from "./viewport3dCameraFov";

describe("viewport 3D camera FOV", () => {
  it("accepts finite FOV values strictly inside the projection limits", () => {
    expect(isViewport3DCameraFovDegreesValid(35)).toBe(true);
    expect(isViewport3DCameraFovDegreesValid(179.9)).toBe(true);
    expect(isViewport3DCameraFovDegreesValid(0)).toBe(false);
    expect(isViewport3DCameraFovDegreesValid(180)).toBe(false);
    expect(isViewport3DCameraFovDegreesValid(Number.NaN)).toBe(false);
    expect(isViewport3DCameraFovDegreesValid(Number.POSITIVE_INFINITY)).toBe(
      false,
    );
  });

  it("resolves missing or invalid camera resources to the shared default", () => {
    expect(resolveViewport3DCameraFovDegrees(35)).toBe(35);
    expect(resolveViewport3DCameraFovDegrees(undefined)).toBe(
      DEFAULT_VIEWPORT_3D_CAMERA_FOV_DEGREES,
    );
    expect(resolveViewport3DCameraFovDegrees(0)).toBe(
      DEFAULT_VIEWPORT_3D_CAMERA_FOV_DEGREES,
    );
    expect(resolveViewport3DCameraFovDegrees(180)).toBe(
      DEFAULT_VIEWPORT_3D_CAMERA_FOV_DEGREES,
    );
  });
});
