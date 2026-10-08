export type AntennaFieldQuantity = "electric_potential_per_ampere" | "current_density_per_ampere" | "magnetic_field_per_ampere" | "device_potential" | "magnetic_field";

export function antennaFieldDisplayLabel(intent: Pick<AntennaFieldIntent, "quantity">): string {
  switch (intent.quantity) {
    case "device_potential": return "V [V]";
    case "magnetic_field": return "H [A/m]";
    case "electric_potential_per_ampere": return "V/I [V/A]";
    case "current_density_per_ampere": return "J/I [A/m^2/A]";
    case "magnetic_field_per_ampere": return "H/I [A/m/A]";
  }
}

/** Client display intent only; never an authored physics module or a field buffer. */
export interface AntennaFieldIntent {
  kind: "basis" | "inspection";
  sessionId: string;
  sessionEpoch: string;
  requestScopeEpoch: string;
  sourceObjectId: string;
  stageId: string;
  solutionId: string;
  contentDigest: string;
  portModeId: string;
  recordContentDigest?: string;
  stageRevision?: number;
  quantity: AntennaFieldQuantity;
  surface?: boolean;
  wireframe?: boolean;
  points: boolean;
  vectors: boolean;
  component: "magnitude" | "x" | "y" | "z";
  palette: "viridis" | "coolwarm";
}

export interface AntennaFieldDisplayStatus {
  intentKey: string;
  status: "loading" | "ready" | "unavailable";
  reason: string;
  sampleCount?: number;
  minimum?: number;
  maximum?: number;
}
