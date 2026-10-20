import { describe, expect, it } from "vitest";

import {
  dimensionFrameBoundsFromProjectedCorners,
  resolveDimensionFrameLabelVisibility,
  type DimensionFrameLabelCandidate,
} from "./dimensionFrameLabelLayout";

const viewport = { height: 80, width: 120 };

function label(
  key: string,
  kind: DimensionFrameLabelCandidate["kind"],
  tickIndex: number | undefined,
  bounds: DimensionFrameLabelCandidate["bounds"],
): DimensionFrameLabelCandidate {
  return { axis: "x", bounds, key, kind, tickIndex };
}

describe("dimension frame label layout", () => {
  it("uses all projected frame corners and drops corners outside clip depth", () => {
    const rect = dimensionFrameBoundsFromProjectedCorners(
      [
        { x: -0.6, y: -0.4, z: 0 },
        { x: 0.6, y: 0.4, z: 0 },
        { x: -0.4, y: 0.6, z: 0 },
        { x: 0.4, y: -0.6, z: 0 },
        { x: 0.9, y: 0.1, z: 0 },
        { x: -0.1, y: -0.9, z: 0 },
        { x: 0.2, y: 0.3, z: 0 },
        { x: 0.99, y: 0.99, z: 1.5 },
      ],
      viewport,
    );

    expect(rect).toEqual({ bottom: 76, left: 24, right: 114, top: 16 });
  });

  it("keeps titles, zero and extrema ahead of colliding ordinary ticks", () => {
    const candidates = [
      label("title:x", "title", undefined, { left: 4, top: 4, right: 24, bottom: 18 }),
      label("tick:zero", "tick", 0, { left: 28, top: 4, right: 39, bottom: 17 }),
      label("tick:min", "tick", -2, { left: 44, top: 4, right: 56, bottom: 17 }),
      label("tick:max", "tick", 2, { left: 68, top: 4, right: 80, bottom: 17 }),
      label("tick:ordinary", "tick", 1, { left: 69, top: 4, right: 84, bottom: 17 }),
      label("tick:offscreen", "tick", 3, { left: 108, top: 4, right: 124, bottom: 17 }),
    ];

    expect(resolveDimensionFrameLabelVisibility(candidates, viewport)).toEqual(
      new Set(["title:x", "tick:zero", "tick:min", "tick:max"]),
    );
  });

  it("uses prior visibility to avoid flicker as new labels approach", () => {
    const candidates = [
      label("tick:kept", "tick", -2, { left: 10, top: 10, right: 25, bottom: 22 }),
      label("tick:new", "tick", 2, { left: 27, top: 10, right: 42, bottom: 22 }),
    ];

    expect(
      resolveDimensionFrameLabelVisibility(
        candidates,
        viewport,
        new Set(["tick:kept"]),
      ),
    ).toEqual(new Set(["tick:kept"]));
  });

  it("keeps labels out of screen-space HUD regions", () => {
    const candidates = [
      label("title:x", "title", undefined, { left: 8, top: 8, right: 30, bottom: 22 }),
      label("tick:zero", "tick", 0, { left: 35, top: 8, right: 48, bottom: 22 }),
      label("tick:visible", "tick", 1, { left: 70, top: 8, right: 84, bottom: 22 }),
    ];

    expect(
      resolveDimensionFrameLabelVisibility(
        candidates,
        viewport,
        new Set(),
        false,
        [{ left: 0, top: 0, right: 60, bottom: 30 }],
      ),
    ).toEqual(new Set(["tick:visible"]));
  });
});
