"use client";
import { useEffect, useEffectEvent, useMemo } from "react";
import type { QuantityCatalogResource } from "@/kernel/api/apiTypes";
import { artifactInspectionQuantity, artifactSelectionForQuantity } from "@/kernel/visualization/artifactFieldSelection";
import { useFieldMetaResource, useStageExecutionResource } from "@/kernel/resources/studyRuntimeResources";
import { useSessionResourceIdentity } from "@/kernel/resources/useSessionStatus";
import { useObjectVisualizationController, useObjectVisualizationSelector } from "@/kernel/visualization/useObjectVisualization";
import type { VisualizationTargetSettings } from "@/kernel/visualization/ObjectVisualizationController";
import { artifactCarrierQueries, admitArtifactFieldCarrier } from "../model/artifactFieldCarrierModel";
import { artifactInspectionOwnerPlan, artifactOverlayLocator, prepareArtifactFieldOverlay, presentArtifactFieldOverlay } from "../model/artifactFieldOverlayModel";
import { useViewport3DArtifactTopology, useViewport3DFieldVectorRequest } from "../viewport3dResources";
import { buildViewport3DFieldResourceRequestId } from "../model/viewport3DFieldDataPlan";

export function useArtifactFieldOverlay(quantityId: string, targetId: string | null, settings: VisualizationTargetSettings, rawOverlayActive: boolean, definitions: ReadonlyArray<{ id?: string; source_object_id?: string }> = [], catalog: QuantityCatalogResource | null = null) {
  const session = useSessionResourceIdentity();
  const enabled = artifactInspectionQuantity(catalog, quantityId) && !rawOverlayActive;
  const controller = useObjectVisualizationController();
  const selection = useObjectVisualizationSelector(snapshot => snapshot.artifactFieldSelection ?? null);
  const execution = useStageExecutionResource({ enabled });
  const owner = useMemo(() => artifactInspectionOwnerPlan(definitions, enabled && execution.status === "ready" && !execution.refreshError ? execution.data : null, session, selection), [enabled, definitions, execution.status, execution.refreshError, execution.data, session, selection]);
  const chosen = useMemo(() => artifactSelectionForQuantity(owner.selected, quantityId), [owner.selected, quantityId]);
  const metadata = useFieldMetaResource({ quantityId, component: "full", scope_kind: "full", stage_id: chosen?.runtimeStageId, carrier_id: chosen?.carrierId, expected_carrier_revision: chosen?.carrierRevision, enabled: enabled && Boolean(chosen), strictErrors: true });
  const plan = useMemo(() => {
    if (!enabled) return { locator: null, error: null };
    const error = owner.error ?? execution.error?.message ?? execution.refreshError?.message ?? metadata.error?.message ?? metadata.refreshError?.message;
    if (error || metadata.status !== "ready" || !chosen) return { locator: null, error: error ?? null };
    try { const locator = artifactOverlayLocator(metadata.data, session, targetId, quantityId === "V_electric" ? "V_electric" : quantityId === "J_charge" ? "J_charge" : "H_ant");
      if (!locator) throw new Error("Selected inspection owner has no immutable field metadata.");
      if (locator && (locator.owner.runtime_stage_id !== chosen.runtimeStageId || locator.owner.run_id !== chosen.runId || locator.owner.authored_stage_id !== chosen.authoredStageId || locator.owner.object_id !== chosen.sourceObjectId || (chosen.carrierId && chosen.carrierId !== locator.carrier_id) || (chosen.carrierRevision && chosen.carrierRevision !== locator.carrier_revision))) throw new Error("Inspection metadata differs from the selected immutable owner.");
      return { locator, error: null }; }
    catch (e) { return { locator: null, error: e instanceof Error ? e.message : "Invalid vector inspection metadata." }; }
  }, [enabled, quantityId, metadata.status, metadata.data, metadata.error, metadata.refreshError, session, targetId, owner.error, chosen, execution.error, execution.refreshError]);
  const publishPin = useEffectEvent(() => {
    if (!plan.locator || !chosen) return;
    const current = controller.getSnapshot().artifactFieldSelection;
    if (current && (JSON.stringify(current.identity) !== JSON.stringify(chosen.identity) || current.runId !== chosen.runId || current.runtimeStageId !== chosen.runtimeStageId || current.authoredStageId !== chosen.authoredStageId || current.sourceObjectId !== chosen.sourceObjectId)) return;
    controller.setArtifactFieldSelection({ identity: chosen.identity, runId: chosen.runId, runtimeStageId: chosen.runtimeStageId, authoredStageId: chosen.authoredStageId, sourceObjectId: chosen.sourceObjectId, quantityId, carrierId: plan.locator.carrier_id, carrierRevision: plan.locator.carrier_revision, carrierScopeKind: plan.locator.carrier_scope_kind, carrierScopeId: plan.locator.carrier_scope_id });
  });
  useEffect(() => publishPin(), [controller, plan.locator, chosen]);
  const queries = useMemo(() => plan.locator ? artifactCarrierQueries(plan.locator) : null, [plan.locator]);
  const request = useMemo(() => { const query = queries?.vector ?? { component: "full" }; return { consumers: ["analysis-complex-field" as const], quantityId, query, requestId: buildViewport3DFieldResourceRequestId(quantityId, query) }; }, [queries, quantityId]);
  const vector = useViewport3DFieldVectorRequest(request, Boolean(queries));
  const topology = useViewport3DArtifactTopology(queries?.geometry ?? null);
  const prepared = useMemo(() => {
    if (!enabled) return { data: null, historical: false, error: null };
    const resourceError = plan.error ?? vector.error?.message ?? vector.refreshError?.message ?? topology.error?.message ?? topology.refreshError?.message;
    if (resourceError) return { data: null, historical: true, error: resourceError };
    if (!queries || !plan.locator || vector.status !== "ready" || topology.status !== "ready" || !vector.data || !vector.responseMetadata || !topology.data) return { data: null, historical: true, error: plan.error };
    try { return { data: prepareArtifactFieldOverlay(admitArtifactFieldCarrier(plan.locator, vector.data, vector.responseMetadata, topology.data, topology.responseMetadata)), historical: true, error: null }; }
    catch (e) { return { data: null, historical: true, error: e instanceof Error ? e.message : "Invalid vector inspection payload." }; }
  }, [enabled, queries, plan, vector.status, vector.data, vector.responseMetadata, topology.status, topology.data, topology.responseMetadata, topology.error, topology.refreshError, vector.error, vector.refreshError]);
  const result = useMemo(() => {
    if (!prepared.data) return { model: null, historical: prepared.historical, error: prepared.error };
    try { return { model: presentArtifactFieldOverlay(prepared.data, settings), historical: true, error: null }; }
    catch (e) { return { model: null, historical: true, error: e instanceof Error ? e.message : "Invalid vector inspection presentation." }; }
  }, [prepared, settings]);
  return { ...result, candidates: enabled ? owner.candidates : [], selectedStageId: chosen?.runtimeStageId ?? "", select: (runtimeStageId: string) => { const c = owner.candidates.find(c => c.runtimeStageId === runtimeStageId); if (c) { const { status: _status, ...pin } = c; controller.setArtifactFieldSelection(pin); } } };
}
