import {
  resolveArtifactAssessment,
  type ArtifactAssessmentInput,
} from "./artifactAssessment";

export type MeshFreshnessState =
  | "building"
  | "current"
  | "failed"
  | "inconsistent"
  | "not-built"
  | "stale"
  | "unknown";

export interface MeshBuildFreshnessInput extends ArtifactAssessmentInput {}

export interface MeshBuildFreshness {
  reason: string;
  state: MeshFreshnessState;
}

/**
 * Adapter delegating to the single canonical artifact assessment resolver
 * (PR08/PR10/D06/A08).
 */
export function resolveMeshBuildFreshness(
  input: MeshBuildFreshnessInput,
): MeshBuildFreshness {
  const assessment = resolveArtifactAssessment(input);
  if (assessment.state === "loading") {
    return { reason: assessment.reason, state: "building" };
  }
  if (assessment.presence === "not-built") {
    return { reason: assessment.reason, state: "not-built" };
  }
  return {
    reason: assessment.reason,
    state: assessment.state ?? "unknown",
  };
}
