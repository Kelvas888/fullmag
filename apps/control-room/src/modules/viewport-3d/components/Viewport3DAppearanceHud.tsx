"use client";

import { Button } from "@/shared/ui/Button";
import { useViewport3DCommandState } from "../viewport3dStore";

export function Viewport3DAppearanceHud({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { appearance, captureError, widgets } = useViewport3DCommandState();
  return <>
    {widgets.dimensionFrameMode !== "off" ? <span title={appearance.dimensionOrigin === "world" ? "Tick values are absolute world coordinates in the displayed unit." : "Tick values are relative to the center of the displayed reference frame."}>Origin: {appearance.dimensionOrigin === "world" ? "world" : "frame center"}</span> : null}
    {appearance.fieldShading ? <span title="Shape shading modulates brightness. Pixel brightness is not a direct numerical legend value.">Field shape shading on</span> : null}
    <Button className="fm-viewport-3d__render-details-trigger" variant="secondary" size="sm" onClick={onOpenSettings}>View settings</Button>
    {captureError ? <span role="alert">Image export failed: {captureError}</span> : null}
  </>;
}
