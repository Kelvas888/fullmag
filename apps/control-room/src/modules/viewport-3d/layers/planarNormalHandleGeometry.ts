type Vec3 = readonly [number, number, number];

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/**
 * Parameter t of the point on the axis line p + t·n closest to the ray
 * o + s·d (s free). Null when the ray is parallel to the axis, where the
 * drag position along the normal is undefined.
 */
export function closestAxisParameter(
  rayOrigin: Vec3,
  rayDirection: Vec3,
  axisPoint: Vec3,
  axisDirection: Vec3,
): number | null {
  const w: Vec3 = [rayOrigin[0] - axisPoint[0], rayOrigin[1] - axisPoint[1], rayOrigin[2] - axisPoint[2]];
  const a = dot(rayDirection, rayDirection);
  const b = dot(rayDirection, axisDirection);
  const c = dot(axisDirection, axisDirection);
  const denominator = a * c - b * b;
  if (!(Math.abs(denominator) > 1e-12 * a * c)) return null;
  return (a * dot(axisDirection, w) - b * dot(rayDirection, w)) / denominator;
}

/** Centre of the monitor's (u, v) bounds in world coordinates. */
export function planarFrameCenter(
  originM: Vec3,
  uAxis: Vec3,
  vAxis: Vec3,
  boundsUvM: readonly [number, number, number, number],
): [number, number, number] {
  const u = (boundsUvM[0] + boundsUvM[1]) / 2;
  const v = (boundsUvM[2] + boundsUvM[3]) / 2;
  return [0, 1, 2].map((axis) => originM[axis]! + u * uAxis[axis]! + v * vAxis[axis]!) as [number, number, number];
}

/** Origin moved by `distance` along the unit normal. */
export function translateAlongNormal(originM: Vec3, normal: Vec3, distance: number): [number, number, number] {
  const length = Math.hypot(normal[0], normal[1], normal[2]) || 1;
  return [0, 1, 2].map((axis) => originM[axis]! + (distance * normal[axis]!) / length) as [number, number, number];
}
