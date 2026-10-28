import { describe, expect, it } from "vitest";

import { closestAxisParameter, planarFrameCenter, translateAlongNormal } from "./planarNormalHandleGeometry";

describe("planar normal handle geometry", () => {
  it("finds the axis point closest to a skew ray", () => {
    // Axis: z through the origin; ray along x at height z = 3, offset y = 1.
    expect(closestAxisParameter([-5, 1, 3], [1, 0, 0], [0, 0, 0], [0, 0, 1])).toBeCloseTo(3, 12);
    // Non-unit axis direction scales the parameter.
    expect(closestAxisParameter([-5, 1, 3], [1, 0, 0], [0, 0, 0], [0, 0, 2])).toBeCloseTo(1.5, 12);
  });

  it("returns null for a ray parallel to the axis", () => {
    expect(closestAxisParameter([1, 1, 0], [0, 0, 1], [0, 0, 0], [0, 0, 1])).toBeNull();
  });

  it("centres the frame and moves the origin along the unit normal", () => {
    expect(planarFrameCenter([0, 0, 1], [1, 0, 0], [0, 1, 0], [-2, 4, -1, 1])).toEqual([1, 0, 1]);
    expect(translateAlongNormal([0, 0, 1], [0, 0, 2], 0.5)).toEqual([0, 0, 1.5]);
  });
});
