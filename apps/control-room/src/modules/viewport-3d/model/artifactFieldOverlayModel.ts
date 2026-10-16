import { buildVertexScalarColors } from "../viewport3dFieldMapping";
import type { StageExecutionResource } from "@/kernel/api/apiTypes";
import type { ArtifactFieldSelection } from "@/kernel/visualization/artifactFieldSelection";
import { artifactSelectionMatchesSession } from "@/kernel/visualization/artifactFieldSelection";
import { scalarColorRgb } from "@/shared/visualization/scalarColorPalette";
import type { VisualizationTargetSettings } from "@/kernel/visualization/ObjectVisualizationController";
import { deviceBoundary, MAX_ANTENNA_DISPLAY_SAMPLES, MAX_ANTENNA_DISPLAY_CELLS, MAX_ANTENNA_DISPLAY_PAYLOAD_BYTES } from "./antennaFieldOverlayModel";
import { admitArtifactFieldCarrier, parseArtifactFieldLocator } from "./artifactFieldCarrierModel";

import { encodeAntennaGlyphSegments } from "./antennaGlyphPresentation";
import { artifactCellLocalBoundary } from "./artifactTet4Boundary";

export function prepareArtifactFieldOverlay(admitted: ReturnType<typeof admitArtifactFieldCarrier>) {
  const { field, topology, locator } = admitted, count = field.pointCount;
  const current = field.quantityId === "J_charge", scalar = field.quantityId === "V_electric";
  const components = scalar ? 1 : 3;
  if ((!current && !scalar && field.quantityId !== "H_ant") || field.nComp !== components ||
      !(scalar ? locator.indexing === "source_nodes" : current ? locator.indexing === "tet4_cell_local_nodes" : ["sample_nodes", "point_samples"].includes(locator.indexing)) ||
      !Number.isSafeInteger(count) || count <= 0 || count > (current ? MAX_ANTENNA_DISPLAY_CELLS * 4 : MAX_ANTENNA_DISPLAY_SAMPLES) ||
      field.values.length !== count * components || topology.positions.byteLength + field.values.byteLength +
      (field.artifactMapping?.identityIds.byteLength ?? 0) + (topology.cellNodes?.byteLength ?? 0) > MAX_ANTENNA_DISPLAY_PAYLOAD_BYTES) {
    throw new Error("Common inspection overlay requires bounded raw H_ant, cell-local J_charge or source-node V_electric.");
  }
  const positions = Float32Array.from(topology.positions);
  if (positions.some(v => !Number.isFinite(v))) throw new Error("Owned coordinates cannot be represented for rendering.");
  const magnitudes = new Float64Array(count), low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
  let maximumNorm = 0;
  for (let i = 0; i < count; i++) {
    const norm = scalar ? 0 : Math.hypot(...field.values.subarray(i * 3, i * 3 + 3));
    if (scalar && !Number.isFinite(field.values[i])) throw new Error("Non-finite raw scalar.");
    if (!Number.isFinite(norm)) throw new Error("Non-finite raw vector magnitude.");
    maximumNorm = Math.max(maximumNorm, norm); magnitudes[i] = norm;
    for (let axis = 0; axis < 3; axis++) { low[axis] = Math.min(low[axis], topology.positions[i * 3 + axis]); high[axis] = Math.max(high[axis], topology.positions[i * 3 + axis]); }
  }
  const extent = Math.hypot(...high.map((v, axis) => v - low[axis]));
  if (!(extent > 0) || !Number.isFinite(extent)) throw new Error("Owned vector samples require physical extent.");
  const cellCount = topology.cellTypes?.length ?? 0;
  let surfaceTriangles: Uint32Array | null = null, surfaceEdges: Uint32Array | null = null;
  if (current) {
    if (cellCount * 4 !== count || !field.artifactMapping) throw new Error("Current surface requires complete cell-local Tet4 mapping.");
    const boundary = artifactCellLocalBoundary(topology.positions, field.artifactMapping.identityIds);
    surfaceTriangles = boundary.triangles; surfaceEdges = boundary.edges;
  } else if (cellCount) {
    if (cellCount > MAX_ANTENNA_DISPLAY_CELLS || !topology.cellTypes || !topology.cellOffsets || !topology.cellNodes
      || topology.cellTypes.some(v => v !== 1) || topology.cellNodes.length !== cellCount * 4
      || topology.cellOffsets.some((v, i) => v !== i * 4)) throw new Error("Common H surface requires its complete owned Tet4 topology.");
    const xyz = new Float64Array(topology.positions), cells = new Uint32Array(topology.cellNodes);
    const boundary = deviceBoundary(xyz.buffer, cells.buffer, count); surfaceTriangles = boundary.triangles; surfaceEdges = boundary.edges;
  }
  const surfaceVectorScale = maximumNorm || 1, surfaceVectorValues = scalar ? new Float32Array(0) : Float32Array.from(field.values, v => v / surfaceVectorScale);
  const surfaceScalarValues = scalar ? buildVertexScalarColors(field, count, MAX_ANTENNA_DISPLAY_SAMPLES, "magnitude", "viridis")?.scalarValues ?? null : null;
  if (scalar && !surfaceScalarValues) throw new Error("Owned potential requires a complete bounded scalar color buffer.");
  if (surfaceScalarValues?.some(v => !Number.isFinite(v))) throw new Error("Owned scalar values cannot be represented for rendering.");
  const allSampleIndices = Uint32Array.from({ length: count }, (_, index) => index);
  const boundaryMask = new Uint8Array(count);
  if (surfaceTriangles) for (const index of surfaceTriangles) boundaryMask[index] = 1;
  const surfaceSampleIndices = surfaceTriangles ? allSampleIndices.filter(index => boundaryMask[index] === 1) : null;
  return { field, locator, count, current, scalar, surfaceScalarValues, positions, magnitudes, maximumNorm, extent, surfaceTriangles, surfaceEdges, surfaceVectorScale, surfaceVectorValues, allSampleIndices, surfaceSampleIndices };
}

export function presentArtifactFieldOverlay(data: ReturnType<typeof prepareArtifactFieldOverlay>, settings: VisualizationTargetSettings) {
  const { field, locator, count, current, scalar, positions, magnitudes, maximumNorm, extent, surfaceTriangles, surfaceEdges, surfaceVectorScale, surfaceVectorValues } = data;
  if (!surfaceTriangles && (settings.shaderVisible || settings.wireframeVisible)) throw new Error("Point samples have no owned surface; enable points or vectors.");
  const component: "scalar" | "x" | "y" | "z" | "magnitude" = scalar ? "scalar" : settings.shaderColorMode === "x" || settings.shaderColorMode === "y" || settings.shaderColorMode === "z" ? settings.shaderColorMode : "magnitude";
  const scalars = new Float64Array(count);
  let minimum = Infinity, maximum = -Infinity;
  for (let i = 0; i < count; i++) {
    scalars[i] = scalar ? field.values[i] : component === "magnitude" ? magnitudes[i] : field.values[i * 3 + (component === "x" ? 0 : component === "y" ? 1 : 2)];
    minimum = Math.min(minimum, scalars[i]); maximum = Math.max(maximum, scalars[i]);
  }
  if (settings.geometryScope === "surface" && !data.surfaceSampleIndices && (settings.pointsVisible || settings.vectorsVisible)) throw new Error("Surface scope requires an owned boundary; choose full scope for point samples.");
  const pointSampleIndices = settings.geometryScope === "surface" ? data.surfaceSampleIndices ?? new Uint32Array(0) : data.allSampleIndices;
  if (!scalar && settings.vectorsVisible && (!Number.isFinite(settings.vectorBudget) || settings.vectorBudget < 0)) throw new Error("Owned vector budget must be finite and non-negative.");
  const glyphCount = scalar || !settings.vectorsVisible ? 0 : Math.min(pointSampleIndices.length, Math.floor(settings.vectorBudget));
  // An explicit display budget samples immutable slots; it never alters source values or surface data.
  const vectorSampleIndices = Uint32Array.from({ length: glyphCount }, (_, index) => pointSampleIndices[
    glyphCount === 1 ? Math.floor((pointSampleIndices.length - 1) / 2) : Math.floor(index * (pointSampleIndices.length - 1) / (glyphCount - 1))
  ]);
  const segments = glyphCount > 0 ? new Float32Array(glyphCount * 6) : null;
  const scale = maximumNorm > 0 ? extent / Math.max(4, Math.cbrt(count)) * .45 * settings.vectorLengthScale / maximumNorm : 0;
  if (segments) for (let i = 0; i < glyphCount; i++) for (let axis = 0; axis < 3; axis++) {
    const source = vectorSampleIndices[i], delta = field.values[source * 3 + axis] * scale;
    segments[i * 6 + axis] = positions[source * 3 + axis] - (settings.vectorCenteringEnabled ? delta / 2 : 0); segments[i * 6 + axis + 3] = segments[i * 6 + axis] + delta;
  }
  if (segments?.some(v => !Number.isFinite(v))) throw new Error("Owned vector glyph cannot be represented.");
  const glyphColors = new Float32Array(glyphCount * 3);
  for (let i = 0; i < glyphCount; i++) glyphColors.set(scalarColorRgb(maximumNorm > 0 ? magnitudes[vectorSampleIndices[i]] / maximumNorm : .5, settings.scalarColorPalette), i * 3);
  const vectorSegments = encodeAntennaGlyphSegments(segments, glyphCount);
  if (vectorSegments) for (let i = 0; i < glyphCount; i++) vectorSegments[i * 7 + 6] = maximumNorm > 0 ? magnitudes[vectorSampleIndices[i]] / maximumNorm : 0;
  const glyphSelectionKey = JSON.stringify([settings.geometryScope ?? "full", glyphCount]);
  const glyphStyleKey = JSON.stringify([settings.geometryScope, settings.vectorBudget, settings.scalarColorPalette, settings.vectorColorMode, settings.vectorLengthScale, settings.vectorCenteringEnabled]);
  return { scalar, geometry: data, glyphColors, glyphSelectionKey, glyphStyleKey, key: `${locator.carrier_id}:${field.fieldGenerationId}:${field.sourceRevision}`, quantityId: field.quantityId as "H_ant" | "J_charge" | "V_electric", unit: scalar ? "V" : current ? "A/m^2" : "A/m",
    status: "historical_inspection" as const, locator, fieldRevision: field.sourceRevision ?? "", positions, scalarValues: scalars, vectorSegments, pointSampleIndices, vectorSampleIndices, glyphCount, availableGlyphCount: pointSampleIndices.length,
    surfaceTriangles, surfaceEdges, surfaceVectorValues, surfaceVectorScale, maximumVectorNorm: scalar ? 0 : maximumNorm, minimum: component === "magnitude" ? 0 : minimum, maximum, count,
    intent: { component, palette: settings.scalarColorPalette }, settings };
}
export function buildArtifactFieldOverlayModel(admitted: ReturnType<typeof admitArtifactFieldCarrier>, settings: VisualizationTargetSettings) {
  return presentArtifactFieldOverlay(prepareArtifactFieldOverlay(admitted), settings);
}
export type ArtifactFieldOverlayModel = ReturnType<typeof buildArtifactFieldOverlayModel>;

/** Strict immutable carrier admission before reading any historical field payload. */
export function artifactOverlayLocator(metadata: unknown, session: { sessionId: string; sessionEpoch: string; requestScopeEpoch: string } | null, targetId: string | null, quantityId: "H_ant" | "J_charge" | "V_electric" = "H_ant") {
  if (!session || !metadata || typeof metadata !== "object") return null;
  const m = metadata as Record<string, unknown>, capability = m.resolved_capability as Record<string, unknown> | undefined;
  const scalar = quantityId === "V_electric", components = scalar ? 1 : 3;
  const unit = scalar ? "V" : quantityId === "J_charge" ? "A/m^2" : "A/m";
  if (!m.artifact_field_locator) return null;
  if (m.quantity_id !== quantityId || m.unit !== unit || m.components !== components || m.state !== "stale_complete" || m.materialization_reason_code !== "historical_inspection_read_only"
    || !capability || capability.quantity_id !== quantityId || capability.provider !== "available" || capability.request !== "field_vector" || capability.materialization !== "materialized"
    || capability.render !== "renderable" || capability.publication !== "interactive" || capability.reason_code !== "historical_inspection_read_only" || capability.lane !== "artifact_inspection_read_only") throw new Error("Vector inspection capability is unavailable.");
  const locator = parseArtifactFieldLocator(m.artifact_field_locator);
  if (!(scalar ? locator.indexing === "source_nodes" : quantityId === "J_charge" ? locator.indexing === "tet4_cell_local_nodes" : ["sample_nodes", "point_samples"].includes(locator.indexing))) throw new Error("Inspection quantity has an incompatible owned indexing.");
  if (locator.owner.session_id !== session.sessionId || locator.owner.session_epoch !== session.sessionEpoch || locator.owner.request_scope_epoch !== session.requestScopeEpoch
    || (locator.carrier_scope_kind === "object" && locator.carrier_scope_id !== targetId)) throw new Error("Vector inspection target/session ownership mismatch.");
  const carriers = capability.carriers;
  if (!Array.isArray(carriers) || carriers.length !== 1) throw new Error("Vector inspection requires one immutable carrier.");
  const c = carriers[0];
  if (c.carrier_id !== locator.carrier_id || c.carrier_fingerprint !== locator.carrier_digest || c.scope_kind !== locator.carrier_scope_kind || (c.scope_id ?? null) !== locator.carrier_scope_id
    || c.payload_state !== "historical" || c.payload_version !== "FMVP.v6" || c.components !== components || c.indexing !== locator.indexing) throw new Error("Vector inspection carrier capability mismatch.");
  return locator;
}

export function artifactInspectionOwnerPlan(definitions: ReadonlyArray<{ id?: string; source_object_id?: string }>, execution: StageExecutionResource | null, identity: { sessionId: string; sessionEpoch: string; requestScopeEpoch: string } | null, selection: ArtifactFieldSelection | null) {
  const candidates: Array<ArtifactFieldSelection & { status: string }> = [];
  if (!identity || !execution) return { candidates, selected: null, error: null };
  if (execution.session_id !== identity.sessionId || execution.session_epoch !== identity.sessionEpoch || execution.request_scope_epoch !== identity.requestScopeEpoch || !execution.run_id) return { candidates, selected: null, error: "Inspection execution belongs to another session." };
  for (const stage of execution.stages) {
    if (!stage.antenna_solve_stage_id) continue;
    const matches = definitions.filter(d => d.id === stage.antenna_solve_stage_id);
    if (matches.length !== 1 || !matches[0].source_object_id || !stage.stage_id || candidates.some(c => c.runtimeStageId === stage.stage_id)) return { candidates: [], selected: null, error: "Inspection definition/source is missing or ambiguous; no nearest result is adopted." };
    candidates.push({ identity, runId: execution.run_id, runtimeStageId: stage.stage_id, authoredStageId: stage.antenna_solve_stage_id, sourceObjectId: matches[0].source_object_id, status: stage.status });
  }
  if (selection) {
    const found = artifactSelectionMatchesSession(selection, identity) && selection.runId === execution.run_id && candidates.find(c => c.runtimeStageId === selection.runtimeStageId && c.authoredStageId === selection.authoredStageId && c.sourceObjectId === selection.sourceObjectId);
    if (!found) return { candidates, selected: null, error: "Selected inspection owner is no longer available; select an execution explicitly." };
    return { candidates, selected: selection, error: null };
  }
  if (candidates.length === 1) return { candidates, selected: candidates[0], error: null };
  return { candidates, selected: null, error: candidates.length > 1 ? "Multiple inspection owners exist. Select a source and execution." : null };
}
