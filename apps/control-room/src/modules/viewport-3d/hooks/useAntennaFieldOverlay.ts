"use client";

import { useEffect, useMemo } from "react";
import { antennaFieldPayloadEtag, antennaInspectionDisplayMatchesOwner, useAntennaFieldSolutionPayloadResource, useAntennaFieldSolutionResource, useAntennaStageOutputCatalogResource, useAntennaExternalLeadInspectionResource, useAntennaInspectionDisplayResource, useAntennaInspectionDisplayPayloadResource } from "@/kernel/resources/antennaResources";
import { useSessionResourceIdentity } from "@/kernel/resources/useSessionStatus";
import { useSelectionSelector } from "@/kernel/selection/useSelection";
import { useObjectVisualizationSelector, useObjectVisualizationController } from "@/kernel/visualization/useObjectVisualization";
import { antennaDisplayShape, antennaDisplayTopologyShape, buildAntennaFieldOverlayModel } from "../model/antennaFieldOverlayModel";

/** One data owner outside the manual R3F root. Binary arrays stay in resource cache / render model. */
export function useAntennaFieldOverlay() {
  const controller = useObjectVisualizationController();
  const requested = useObjectVisualizationSelector((snapshot) => snapshot.antennaFieldIntent ?? null);
  const owner = useSessionResourceIdentity();
  const selectedObjectId = useSelectionSelector((selection) => selection.ref?.type === "scene-object" ? selection.ref.objectId : selection.objectId);
  const intent = requested && owner && requested.sessionId === owner.sessionId &&
    requested.sessionEpoch === owner.sessionEpoch && requested.requestScopeEpoch === owner.requestScopeEpoch &&
    requested.sourceObjectId === selectedObjectId && (requested.points || requested.vectors || requested.surface || requested.wireframe) ? requested : null;
  const solution = useAntennaFieldSolutionResource(intent?.kind === "basis" ? intent.solutionId : null);
  const catalog = useAntennaStageOutputCatalogResource(intent?.kind === "basis" ? intent.stageId : null);
  const inspection = useAntennaExternalLeadInspectionResource(intent?.kind === "inspection" ? intent.stageId : null);
  const raw = inspection.data;
  const inspectionOwnerMatches = Boolean(intent?.kind === "inspection" && inspection.status === "ready" && raw &&
    raw.session_id === intent.sessionId && raw.session_epoch === intent.sessionEpoch && raw.request_scope_epoch === intent.requestScopeEpoch &&
    raw.runtime_stage_id === intent.stageId && raw.stage_revision === intent.stageRevision && raw.record_content_digest === intent.recordContentDigest &&
    raw.manifest?.source_object_id === intent.sourceObjectId && raw.manifest.content_digest === intent.contentDigest && raw.port_mode_id === intent.portModeId);
  const display = useAntennaInspectionDisplayResource(inspectionOwnerMatches ? raw : null);
  const inspectionPlan = useMemo(() => {
    const data = inspection.data;
    const metadata = display.data;
    if (!intent || intent.kind !== "inspection" || !inspectionOwnerMatches || !data || display.status !== "ready" || !metadata ||
        !antennaInspectionDisplayMatchesOwner(data, metadata)) return null;
    const scalar = intent.quantity === "device_potential";
    if (!scalar && intent.quantity !== "magnetic_field") return null;
    const positionKind = scalar ? "device_positions" as const : "sample_positions" as const;
    const valueKind = scalar ? "device_potential" as const : "magnetic_field" as const;
    const positions = metadata[positionKind], values = metadata[valueKind];
    try {
      const count = antennaDisplayShape(positions, values, intent);
      if (scalar) antennaDisplayTopologyShape(metadata.device_topology, count, metadata.device_cell_count, positions, values);
      if (count !== (scalar ? metadata.device_node_count : metadata.sampling_carrier.sample_count)) return null;
      return { data, metadata, count, positionKind, valueKind, positions, values, topology: scalar ? metadata.device_topology : null };
    }
    catch { return null; }
  }, [intent, inspection.data, inspectionOwnerMatches, display.data, display.status]);
  const plan = useMemo(() => {
    if (!intent || intent.kind !== "basis" || solution.status !== "ready" || catalog.status !== "ready") return null;
    const data = solution.data;
    const stage = catalog.data;
    const output = stage?.outputs.find((item) => item.output_id === intent.solutionId);
    if (!data || !stage || data.status !== "ready" || stage.status !== "ready" ||
        data.solution_id !== intent.solutionId || data.stage_id !== intent.stageId || data.quantity !== "H_ant_basis" ||
        data.source_object_id !== intent.sourceObjectId || data.content_digest !== intent.contentDigest ||
        data.session_id !== intent.sessionId || data.session_epoch !== intent.sessionEpoch || data.request_scope_epoch !== intent.requestScopeEpoch ||
        stage.stage_id !== intent.stageId || stage.session_id !== intent.sessionId || stage.session_epoch !== intent.sessionEpoch || stage.request_scope_epoch !== intent.requestScopeEpoch ||
        output?.solution_ref.content_digest !== intent.contentDigest || output.solution_ref.asset_id !== data.asset_id || output.solution_ref.stage_id !== intent.stageId) return null;
    const basis = data.bases.find((candidate) => candidate.port_mode_id === intent.portModeId);
    if (!basis) return null;
    const quantity = intent.quantity;
    if (quantity === "device_potential" || quantity === "magnetic_field") return null;
    const positionKind = quantity === "magnetic_field_per_ampere" ? "sample_positions" as const : "conductor_positions" as const;
    const positions = data[positionKind];
    const values = basis[quantity];
    try {
      const count = antennaDisplayShape(positions, values, intent);
      return { count, quantity, positionKind, positions, values,
        positionEtag: antennaFieldPayloadEtag(data, positionKind),
        fieldEtag: antennaFieldPayloadEtag(data, quantity, intent.portModeId) };
    } catch { return null; }
  }, [intent, solution.data, solution.status, catalog.data, catalog.status]);
  const positions = useAntennaFieldSolutionPayloadResource(plan ? intent?.solutionId : null, plan?.positionKind, null, {
    enabled: Boolean(plan), expectedEtag: plan?.positionEtag,
    maxResponseBytes: plan ? plan.positions.value_count * 8 : undefined,
    range: plan ? `bytes=0-${plan.positions.value_count * 8 - 1}` : undefined,
  });
  const field = useAntennaFieldSolutionPayloadResource(plan ? intent?.solutionId : null, plan?.quantity, intent?.portModeId, {
    enabled: Boolean(plan), expectedEtag: plan?.fieldEtag,
    maxResponseBytes: plan ? plan.values.value_count * 8 : undefined,
    range: plan ? `bytes=0-${plan.values.value_count * 8 - 1}` : undefined,
  });
  const inspectionPositions = useAntennaInspectionDisplayPayloadResource(inspectionPlan?.data, inspectionPlan?.metadata, inspectionPlan?.positionKind, {
    enabled: Boolean(inspectionPlan), maxResponseBytes: inspectionPlan?.positions.byte_count, range: inspectionPlan ? `bytes=0-${inspectionPlan.positions.byte_count - 1}` : undefined,
  });
  const inspectionField = useAntennaInspectionDisplayPayloadResource(inspectionPlan?.data, inspectionPlan?.metadata, inspectionPlan?.valueKind, {
    enabled: Boolean(inspectionPlan), maxResponseBytes: inspectionPlan?.values.byte_count, range: inspectionPlan ? `bytes=0-${inspectionPlan.values.byte_count - 1}` : undefined,
  });
  const inspectionTopology = useAntennaInspectionDisplayPayloadResource(inspectionPlan?.data, inspectionPlan?.metadata, inspectionPlan?.topology ? "device_topology" : null, {
    enabled: Boolean(inspectionPlan?.topology), maxResponseBytes: inspectionPlan?.topology?.byte_count, range: inspectionPlan?.topology ? `bytes=0-${inspectionPlan.topology.byte_count - 1}` : undefined,
  });
  const result = useMemo(() => {
    if (intent?.kind === "inspection" && inspectionPlan && inspectionPositions.status === "ready" && inspectionField.status === "ready" &&
        inspectionPositions.data?.status === "ready" && inspectionField.data?.status === "ready" &&
        (!inspectionPlan.topology || inspectionTopology.status === "ready" && inspectionTopology.data?.status === "ready")) {
      try { return { model: buildAntennaFieldOverlayModel(inspectionPositions.data.data, inspectionField.data.data, inspectionPlan.count, intent, inspectionTopology.data?.status === "ready" ? inspectionTopology.data.data : undefined), error: null }; }
      catch (error) { return { model: null, error: error instanceof Error ? error.message : String(error) }; }
    }
    if (!intent || !plan || positions.status !== "ready" || field.status !== "ready" ||
        positions.data?.status !== "ready" || field.data?.status !== "ready" ||
        positions.data.etag !== plan.positionEtag || field.data.etag !== plan.fieldEtag) return null;
    try { return { model: buildAntennaFieldOverlayModel(positions.data.data, field.data.data, plan.count, intent), error: null }; }
    catch (error) { return { model: null, error: error instanceof Error ? error.message : String(error) }; }
  }, [intent, plan, positions.data, positions.status, field.data, field.status, inspectionPlan, inspectionPositions.data, inspectionPositions.status, inspectionField.data, inspectionField.status, inspectionTopology.data, inspectionTopology.status]);
  const model = result?.model ?? null;
  const error = result?.error ?? solution.error?.message ?? catalog.error?.message ?? inspection.error?.message ?? display.error?.message ?? positions.error?.message ?? field.error?.message ?? inspectionPositions.error?.message ?? inspectionField.error?.message ?? inspectionTopology.error?.message;
  const metadataReady = intent?.kind === "inspection" ? inspection.status === "ready" && display.status === "ready" : solution.status === "ready" && catalog.status === "ready";
  const status = useMemo(() => !intent ? null : model ? {
    intentKey: JSON.stringify(intent), status: "ready" as const, reason: model.surfaceTriangles ? "Complete pinned SI device Tet4 carrier and nodal V; exterior surface derived from actual cell connectivity" : "Complete pinned SI sample carrier; no surface interpolation", sampleCount: model.count, minimum: model.minimum, maximum: model.maximum,
  } : {
    intentKey: JSON.stringify(intent), status: error || (metadataReady && !plan && !inspectionPlan) ? "unavailable" as const : "loading" as const,
    reason: error ?? (metadataReady && !plan && !inspectionPlan ? "Incompatible identity, port, layout, units, cardinality or display memory limit. No field was rendered." : "Loading complete, revision-checked sample payloads"),
  }, [intent, model, error, metadataReady, plan, inspectionPlan]);
  useEffect(() => { controller.setAntennaFieldDisplayStatus(status); }, [controller, status]);
  useEffect(() => () => controller.setAntennaFieldDisplayStatus(null), [controller]);
  return model;
}
