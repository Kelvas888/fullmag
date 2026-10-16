import type { QuantityCatalogResource } from "../api/apiTypes";
import { quantityCatalogEntrySupportsSpatialVisualization } from "../api/quantityIds";
import type { SessionResourceIdentity } from "../resources/sessionResourceIdentity";

/** Client-owned immutable inspection selection; never a physics activation. */
export interface ArtifactFieldSelection {
  identity: SessionResourceIdentity;
  runId: string;
  runtimeStageId: string;
  authoredStageId: string;
  sourceObjectId: string;
  /** Carrier pins belong to this quantity; source/run selection is shared. */
  quantityId?: string;
  carrierId?: string;
  carrierRevision?: string;
  carrierScopeKind?: "object" | "full";
  carrierScopeId?: string | null;
}
export function artifactSelectionMatchesSession(selection: ArtifactFieldSelection | null, identity: SessionResourceIdentity | null): boolean {
  return Boolean(selection && identity && selection.identity.sessionId === identity.sessionId && selection.identity.sessionEpoch === identity.sessionEpoch && selection.identity.requestScopeEpoch === identity.requestScopeEpoch);
}

/** Historical artifact routing never follows a quantity name alone. */
export function artifactInspectionQuantity(catalog: QuantityCatalogResource | null, quantityId: string): boolean {
  if (quantityId !== "H_ant" && quantityId !== "J_charge" && quantityId !== "V_electric") return false;
  const entries = catalog?.quantities.filter(entry => entry.id === quantityId) ?? [];
  if (entries.length !== 1) return false;
  const entry = entries[0], capability = entry.resolved_capability, components = quantityId === "V_electric" ? 1 : 3;
  return Boolean(entry.n_comp === components && entry.unit === (quantityId === "V_electric" ? "V" : quantityId === "J_charge" ? "A/m^2" : "A/m") &&
    quantityCatalogEntrySupportsSpatialVisualization(entry) && capability?.quantity_id === quantityId &&
    capability.lane === "artifact_inspection_read_only" && capability.materialization === "materialized" &&
    capability.carriers.some(carrier => carrier.payload_state === "historical" && carrier.components === components &&
      (quantityId === "V_electric" ? carrier.indexing === "source_nodes" : quantityId === "J_charge" ? carrier.indexing === "tet4_cell_local_nodes" : ["sample_nodes", "point_samples"].includes(carrier.indexing))));
}

export function artifactSelectionForQuantity(selection: ArtifactFieldSelection | null, quantityId: string): ArtifactFieldSelection | null {
  if (!selection || selection.quantityId === quantityId) return selection;
  return { identity: selection.identity, runId: selection.runId, runtimeStageId: selection.runtimeStageId,
    authoredStageId: selection.authoredStageId, sourceObjectId: selection.sourceObjectId, quantityId };
}
