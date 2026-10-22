type HudAnchor = [number, number, number];

interface OrientationHudViewport {
  height: number;
  width: number;
}

const ORIENTATION_VIEW_CUBE_MARGIN_PX = 104;
const HSL_REFERENCE_MARGIN_PX = 96;

export function resolveOrientationHudAnchors({
  height,
  width,
}: OrientationHudViewport): {
  hslReference: HudAnchor;
  viewCube: HudAnchor;
} {
  const compact = width < 640 || height < 420;
  const cubeMargin = compact ? 72 : ORIENTATION_VIEW_CUBE_MARGIN_PX;
  const hslMargin = compact ? 64 : HSL_REFERENCE_MARGIN_PX;
  return {
    hslReference: [
      -width / 2 + hslMargin,
      -height / 2 + hslMargin,
      0,
    ],
    viewCube: [
      width / 2 - cubeMargin,
      height / 2 - cubeMargin,
      0,
    ],
  };
}
