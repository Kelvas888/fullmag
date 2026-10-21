export const DEFAULT_VIEWPORT_3D_CAMERA_FOV_DEGREES = 42;

export function isViewport3DCameraFovDegreesValid(
  value: unknown,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value > 0 &&
    value < 180
  );
}

export function resolveViewport3DCameraFovDegrees(value: unknown): number {
  return isViewport3DCameraFovDegreesValid(value)
    ? value
    : DEFAULT_VIEWPORT_3D_CAMERA_FOV_DEGREES;
}
