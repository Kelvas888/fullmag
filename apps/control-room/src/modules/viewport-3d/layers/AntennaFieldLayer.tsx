"use client";

import { useEffect, useMemo } from "react";
import { BufferAttribute, BufferGeometry, DoubleSide, LineBasicMaterial, MeshBasicMaterial, PointsMaterial } from "three";
import { antennaFieldDisplayLabel } from "@/kernel/visualization/antennaFieldIntent";
import type { SessionResourceIdentity } from "@/kernel/resources/sessionResourceIdentity";
import { scalarColorRgb } from "@/shared/visualization/scalarColorPalette";
import type { AntennaFieldOverlayModel } from "../model/antennaFieldOverlayModel";
import type { Viewport3DResourceTracker } from "../viewport3dDiagnostics";
import type { Viewport3DColors } from "../viewport3dTypes";
import { useBatchedInvalidate } from "../viewport3dBatchedInvalidate";
import { VectorFieldLayer } from "./VectorFieldLayer";

/** An actual sample carrier, not a primitive-object field or fabricated surface. */
export function AntennaFieldLayer({ model, colors, tracker, sessionIdentity }: {
  model: AntennaFieldOverlayModel | null;
  colors: Viewport3DColors;
  tracker: Viewport3DResourceTracker;
  sessionIdentity: SessionResourceIdentity | null;
}) {
  const invalidate = useBatchedInvalidate();
  const wireColor = colors.wire;
  const resources = useMemo(() => {
    if (!model) return null;
    const rgb = new Float32Array(model.count * 3);
    const scale = Math.max(Math.abs(model.minimum), Math.abs(model.maximum)) || 1;
    const minimum = model.minimum / scale, range = model.maximum / scale - minimum;
    for (let index = 0; index < model.count; index += 1) {
      rgb.set(scalarColorRgb(range > 0 ? (model.scalarValues[index] / scale - minimum) / range : 0.5, model.intent.palette), index * 3);
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(model.positions, 3));
    geometry.setAttribute("color", new BufferAttribute(rgb, 3));
    geometry.computeBoundingSphere();
    const material = new PointsMaterial({ size: 5, sizeAttenuation: false, vertexColors: true, depthTest: true, depthWrite: true });
    const surface = model.surfaceTriangles ? new BufferGeometry() : null;
    if (surface) {
      surface.setAttribute("position", new BufferAttribute(model.positions, 3));
      surface.setAttribute("color", new BufferAttribute(rgb, 3));
      surface.setIndex(new BufferAttribute(model.surfaceTriangles!, 1));
      surface.computeBoundingSphere();
    }
    const surfaceMaterial = surface ? new MeshBasicMaterial({ vertexColors: true, side: DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }) : null;
    const wireframe = model.surfaceEdges ? new BufferGeometry() : null;
    if (wireframe) {
      wireframe.setAttribute("position", new BufferAttribute(model.positions, 3));
      wireframe.setIndex(new BufferAttribute(model.surfaceEdges!, 1));
      wireframe.computeBoundingSphere();
    }
    const wireMaterial = wireframe ? new LineBasicMaterial({ color: wireColor, depthTest: true }) : null;
    return { geometry, material, rgb, surface, surfaceMaterial, wireframe, wireMaterial };
  }, [model, wireColor]);
  useEffect(() => {
    if (!resources) { invalidate(); return; }
    tracker.track("geometry", resources.geometry, { byteLength: resources.geometry.getAttribute("position").array.byteLength + resources.rgb.byteLength, owner: "antenna-field" });
    tracker.track("material", resources.material, { owner: "antenna-field" });
    if (resources.surface) tracker.track("geometry", resources.surface, { byteLength: model?.surfaceTriangles?.byteLength ?? 0, owner: "antenna-field-surface" });
    if (resources.surfaceMaterial) tracker.track("material", resources.surfaceMaterial, { owner: "antenna-field-surface" });
    if (resources.wireframe) tracker.track("geometry", resources.wireframe, { byteLength: model?.surfaceEdges?.byteLength ?? 0, owner: "antenna-field-wireframe" });
    if (resources.wireMaterial) tracker.track("material", resources.wireMaterial, { owner: "antenna-field-wireframe" });
    invalidate();
    return () => {
      tracker.release("geometry", resources.geometry);
      tracker.release("material", resources.material);
      if (resources.surface) tracker.release("geometry", resources.surface);
      if (resources.surfaceMaterial) tracker.release("material", resources.surfaceMaterial);
      if (resources.wireframe) tracker.release("geometry", resources.wireframe);
      if (resources.wireMaterial) tracker.release("material", resources.wireMaterial);
      invalidate();
    };
  }, [resources, tracker, invalidate, model?.surfaceTriangles?.byteLength, model?.surfaceEdges?.byteLength]);
  const reference = useMemo(() => model ? {
    buildKey: model.key, fieldBufferId: model.key, fieldRevision: model.intent.contentDigest,
    groupKey: `antenna:${model.intent.sourceObjectId}`, resourceKey: model.intent.solutionId,
    revisionSummary: model.key, targetRevision: model.intent.contentDigest,
    topologyRevision: `sample-carrier:${model.intent.contentDigest}`,
  } : null, [model]);
  if (!model || !resources) return null;
  return <group name="antenna-scientific-field" userData={{ quantity: model.intent.quantity, label: antennaFieldDisplayLabel(model.intent), normalization: model.intent.kind === "basis" ? "per_ampere" : "raw_authored_current", sampleCount: model.count, minimum: model.minimum, maximum: model.maximum }}>
    {model.intent.surface && resources.surface && resources.surfaceMaterial ? <mesh name="antenna-field-surface" geometry={resources.surface} material={resources.surfaceMaterial} dispose={null} /> : null}
    {model.intent.wireframe && resources.wireframe && resources.wireMaterial ? <lineSegments name="antenna-field-wireframe" geometry={resources.wireframe} material={resources.wireMaterial} dispose={null} /> : null}
    {model.intent.points ? <points name="antenna-field-samples" geometry={resources.geometry} material={resources.material} dispose={null} /> : null}
    {model.intent.vectors && model.vectorSegments ? <VectorFieldLayer
      segments={model.vectorSegments} buildReference={reference} carrierId={`antenna:${model.intent.sourceObjectId}:${model.intent.portModeId}`}
      fieldBufferId={model.key} colors={colors} colorMode="magnitude" glyphColorsOverride={resources.rgb}
      tracker={tracker} sessionIdentity={sessionIdentity} renderOnTop={false}
    /> : null}
  </group>;
}
