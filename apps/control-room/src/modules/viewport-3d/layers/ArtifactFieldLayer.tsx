"use client";
import { useEffect, useMemo } from "react";
import { BufferAttribute, BufferGeometry, Color, LineBasicMaterial, PointsMaterial, MeshBasicMaterial, DoubleSide, type ShaderMaterial } from "three";
import { pointColorFromSettings, surfaceMaterialColorFromSettings, vectorStyleFromSettings, wireframeColorFromSettings } from "./viewport3DLayerSettings";
import type { SessionResourceIdentity } from "@/kernel/resources/sessionResourceIdentity";
import type { ArtifactFieldOverlayModel } from "../model/artifactFieldOverlayModel";
import type { Viewport3DColors } from "../viewport3dTypes";
import type { Viewport3DResourceTracker } from "../viewport3dDiagnostics";
import { useBatchedInvalidate } from "../viewport3dBatchedInvalidate";
import { VectorFieldLayer } from "./VectorFieldLayer";
import { createAntennaCurrentSurfaceMaterial, updateAntennaCurrentSurfaceMaterial } from "./antennaCurrentSurfaceMaterial";

import { createScalarSurfaceShaderMaterial, updateScalarSurfaceShaderMaterial, VIEWPORT_3D_SCALAR_VALUE_ATTRIBUTE } from "../viewport3dScalarSurfaceShader";
import type { ScalarColorBuffer } from "../viewport3dFieldMapping";

function potentialColorBuffer(model: ArtifactFieldOverlayModel): ScalarColorBuffer {
  return { colors: new Float32Array(0), scalarValues: model.geometry.surfaceScalarValues ?? undefined, colorMode: "magnitude", colorPalette: model.settings.scalarColorPalette, range: { min: model.minimum, max: model.maximum }, quantityId: model.quantityId };
}

/** Three resources are mutable renderer-owned objects, independent of React snapshots. */
function updateArtifactFieldMaterials(owned: { points: PointsMaterial; wireMaterial: LineBasicMaterial; fieldSurface: ReturnType<typeof createAntennaCurrentSurfaceMaterial> | null; scalarSurface: ShaderMaterial | null; scalarSolid: MeshBasicMaterial | null }, model: ArtifactFieldOverlayModel, colors: Pick<Viewport3DColors, "wire" | "mesh">) {
  owned.points.color.set(pointColorFromSettings(model.settings, colors.wire));
  if (owned.points.transparent !== (model.settings.pointOpacityPercent < 100)) {
    owned.points.transparent = model.settings.pointOpacityPercent < 100;
    owned.points.needsUpdate = true;
  }
  owned.points.opacity = model.settings.pointOpacityPercent / 100;
  owned.wireMaterial.color.set(wireframeColorFromSettings(model.settings, colors.wire));
  if (owned.wireMaterial.transparent !== (model.settings.wireframeOpacityPercent < 100)) {
    owned.wireMaterial.transparent = model.settings.wireframeOpacityPercent < 100;
    owned.wireMaterial.needsUpdate = true;
  }
  owned.wireMaterial.opacity = model.settings.wireframeOpacityPercent / 100;
  if (owned.scalarSolid) {
    const transparent = model.settings.surfaceOpacityPercent < 100;
    if (owned.scalarSolid.transparent !== transparent) { owned.scalarSolid.transparent = transparent; owned.scalarSolid.needsUpdate = true; }
    owned.scalarSolid.depthWrite = !transparent;
    owned.scalarSolid.opacity = model.settings.surfaceOpacityPercent / 100;
    owned.scalarSolid.color.set(surfaceMaterialColorFromSettings(model.settings, colors.mesh, false));
  }
  const component = model.intent.component;
  if (owned.scalarSurface) {
    const transparent = model.settings.surfaceOpacityPercent < 100;
    if (owned.scalarSurface.transparent !== transparent) { owned.scalarSurface.transparent = transparent; owned.scalarSurface.needsUpdate = true; }
    owned.scalarSurface.depthWrite = !transparent;
    updateScalarSurfaceShaderMaterial(owned.scalarSurface, potentialColorBuffer(model), model.settings.surfaceOpacityPercent / 100, 0);
  }
  if (owned.fieldSurface && component !== "scalar") updateAntennaCurrentSurfaceMaterial(owned.fieldSurface.material, owned.fieldSurface.palette, { ...model, intent: { ...model.intent, component } }, { colorMode: model.settings.surfaceColorSource === "solid" ? "monochrome" : model.settings.shaderColorMode, monoColor: new Color(surfaceMaterialColorFromSettings(model.settings, colors.mesh, false)).getStyle(), opacity: model.settings.surfaceOpacityPercent / 100 });
}

/** Update the renderer-owned index allocation without replacing its GPU buffer. */
function updateArtifactPointScope(owned: { geometry: BufferGeometry; pointSelection: Uint32Array }, selection: Uint32Array) {
  if (owned.pointSelection === selection || !owned.geometry.index) return;
  (owned.geometry.index.array as Uint32Array).set(selection);
  owned.geometry.index.needsUpdate = true;
  owned.geometry.setDrawRange(0, selection.length);
  owned.pointSelection = selection;
}

/** Positions already belong to world coordinates; this root group has identity transform. */
export function ArtifactFieldLayer({ model, colors, tracker, sessionIdentity }: { model: ArtifactFieldOverlayModel | null; colors: Viewport3DColors; tracker: Viewport3DResourceTracker; sessionIdentity: SessionResourceIdentity | null }) {
  const invalidate = useBatchedInvalidate();
  const data = model?.geometry;
  const owned = useMemo(() => {
    if (!data) return null;
    const geometry = new BufferGeometry(); geometry.setAttribute("position", new BufferAttribute(data.positions, 3)); geometry.setIndex(new BufferAttribute(data.allSampleIndices.slice(), 1)); geometry.setDrawRange(0, data.count); geometry.computeBoundingSphere();
    const surface = data.surfaceTriangles ? new BufferGeometry() : null;
    if (surface) { surface.setAttribute("position", new BufferAttribute(data.positions, 3)); if (data.scalar && data.surfaceScalarValues) surface.setAttribute(VIEWPORT_3D_SCALAR_VALUE_ATTRIBUTE, new BufferAttribute(data.surfaceScalarValues, 1)); else surface.setAttribute("fmAntennaCurrentVector", new BufferAttribute(data.surfaceVectorValues, 3)); surface.setIndex(new BufferAttribute(data.surfaceTriangles!, 1)); surface.computeVertexNormals(); surface.computeBoundingSphere(); }
    const wire = data.surfaceEdges ? new BufferGeometry() : null;
    if (wire) { wire.setAttribute("position", new BufferAttribute(data.positions, 3)); wire.setIndex(new BufferAttribute(data.surfaceEdges!, 1)); wire.computeBoundingSphere(); }
    const points = new PointsMaterial({ size: 5, sizeAttenuation: false, vertexColors: false });
    const fieldSurface = surface && !data.scalar ? createAntennaCurrentSurfaceMaterial() : null;
    const scalarSurface = surface && data.scalar && data.surfaceScalarValues ? createScalarSurfaceShaderMaterial({ colors: new Float32Array(0), scalarValues: data.surfaceScalarValues, range: { min: 0, max: 1 } }, { depthTest: true, depthWrite: true, opacity: 1, transparent: false, side: DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, shadeStrength: 0 }) : null;
    const scalarSolid = surface && data.scalar ? new MeshBasicMaterial({ side: DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, toneMapped: false }) : null;
    const wireMaterial = new LineBasicMaterial();
    return { geometry, pointSelection: data.allSampleIndices, surface, wire, points, fieldSurface, scalarSurface, scalarSolid, wireMaterial };
  }, [data]);
  useEffect(() => {
    if (!owned) { invalidate(); return; }
    for (const geometry of [owned.geometry, owned.surface, owned.wire]) if (geometry) tracker.track("geometry", geometry, { byteLength: Object.values(geometry.attributes).reduce((n, a) => n + a.array.byteLength, geometry.index?.array.byteLength ?? 0), owner: "artifact-field" });
    for (const material of [owned.points, owned.fieldSurface?.material, owned.scalarSurface, owned.scalarSolid, owned.wireMaterial]) if (material) tracker.track("material", material, { owner: "artifact-field" });
    if (owned.fieldSurface) tracker.track("texture", owned.fieldSurface.palette, { byteLength: 1024, owner: "artifact-field" });
    invalidate();
    return () => { for (const geometry of [owned.geometry, owned.surface, owned.wire]) if (geometry) tracker.release("geometry", geometry); for (const material of [owned.points, owned.fieldSurface?.material, owned.scalarSurface, owned.scalarSolid, owned.wireMaterial]) if (material) tracker.release("material", material); if (owned.fieldSurface) tracker.release("texture", owned.fieldSurface.palette); invalidate(); };
  }, [owned, tracker, invalidate]);
  useEffect(() => {
    if (!owned || !model) return;
    updateArtifactPointScope(owned, model.pointSampleIndices);
    updateArtifactFieldMaterials(owned, model, { wire: colors.wire, mesh: colors.mesh });
    invalidate();
  }, [owned, model, colors.wire, colors.mesh, invalidate]);
  const reference = useMemo(() => model ? { buildKey: `${model.key}:glyphs:${model.glyphStyleKey}`, fieldBufferId: model.key, fieldRevision: model.fieldRevision,
    groupKey: `${model.key}:${model.glyphSelectionKey}`, resourceKey: model.locator.carrier_id, revisionSummary: model.key,
    targetRevision: model.locator.carrier_revision, topologyRevision: model.locator.carrier_revision } : null, [model]);
  const vectorStyle = useMemo(() => model ? vectorStyleFromSettings(model.settings, { monoColor: new Color(colors.field).getStyle() }) : undefined, [model, colors.field]);
  if (!model || !owned || !model.settings.visible) return null;
  return <group name={`artifact-historical-${model.quantityId}`} userData={{ quantity: model.quantityId, unit: model.unit, status: "historical_inspection", carrierId: model.locator.carrier_id, availableGlyphCount: model.availableGlyphCount, glyphCount: model.glyphCount, geometryScope: model.settings.geometryScope }}>
    {model.settings.shaderVisible && owned.surface && (owned.fieldSurface || owned.scalarSurface) ? <mesh geometry={owned.surface} material={model.scalar && model.settings.surfaceColorSource === "solid" ? owned.scalarSolid! : owned.scalarSurface ?? owned.fieldSurface!.material} dispose={null} /> : null}
    {model.settings.wireframeVisible && owned.wire ? <lineSegments geometry={owned.wire} material={owned.wireMaterial} dispose={null} /> : null}
    {model.settings.pointsVisible ? <points geometry={owned.geometry} material={owned.points} dispose={null} /> : null}
    {!model.scalar && model.settings.vectorsVisible && model.vectorSegments ? <VectorFieldLayer segments={model.vectorSegments} buildReference={reference} carrierId={model.locator.carrier_id} fieldBufferId={model.key} colors={colors} colorMode={model.settings.vectorColorMode} glyphColorsOverride={model.settings.vectorColorMode === "magnitude" ? model.glyphColors : null} opacity={model.settings.vectorAlphaPercent / 100} style={vectorStyle} tracker={tracker} sessionIdentity={sessionIdentity} renderOnTop={false} /> : null}
  </group>;
}
