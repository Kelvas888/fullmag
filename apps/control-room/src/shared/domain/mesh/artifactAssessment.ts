export type ArtifactPresence = "not-built" | "present";

export type ResourceLoadState = "idle" | "loading" | "ready" | "error" | "stale";

export type ArtifactAssessmentState =
  | "current"
  | "stale"
  | "incompatible"
  | "inconsistent"
  | "unknown"
  | "loading";

export interface ArtifactAssessmentInput {
  activeBuild?: Record<string, unknown> | null;
  latestBuild?: Record<string, unknown> | null;
  manifest?: Record<string, unknown> | null;
  resourceLoadState?: ResourceLoadState;
  sceneRevision?: number | string | null;
  statusMeshRevision?: number | string | null;
}

export interface ArtifactAssessment {
  evidence: "legacy-revision" | "digest";
  presence: ArtifactPresence;
  reason: string;
  runAllowed: boolean;
  state: ArtifactAssessmentState | null;
}

const ACTIVE_STATUSES = new Set([
  "active",
  "building",
  "generating",
  "pending",
  "queued",
  "running",
  "started",
]);

function status(value: Record<string, unknown> | null | undefined): string {
  return typeof value?.status === "string" ? value.status.toLowerCase() : "";
}

function parseRevision(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function meshRevisionIsMissing(value: number | null): boolean {
  return value === null || value <= 0;
}

function sourceSceneRevision(
  value: Record<string, unknown> | null | undefined,
): number | null {
  return parseRevision(value?.source_scene_revision);
}

/**
 * Pure domain resolver for mesh artifact freshness and presence.
 * Satisfies the single-resolver contract of Fullmag audit v2 (PR08/PR10/D06).
 */
export function resolveArtifactAssessment(
  input: ArtifactAssessmentInput,
): ArtifactAssessment {
  const meshRevision = parseRevision(input.statusMeshRevision);
  const manifestSourceRev = sourceSceneRevision(input.manifest);
  const sceneRev = parseRevision(input.sceneRevision);
  const activeStatus = status(input.activeBuild);
  const isBuilding = ACTIVE_STATUSES.has(activeStatus);

  // 1. Legal not-built presence check
  if ((meshRevisionIsMissing(meshRevision) && manifestSourceRev === null) || !input.manifest) {
    return {
      evidence: "legacy-revision",
      presence: "not-built",
      reason: "no mesh artifact has been built yet",
      runAllowed: false,
      state: null,
    };
  }

  // 2. Active building state
  if (isBuilding) {
    return {
      evidence: "legacy-revision",
      presence: "present",
      reason: `active build status is ${activeStatus}`,
      runAllowed: false,
      state: "loading",
    };
  }

  // 3. Inconsistent: source revision is ahead of known scene revision (F19)
  if (
    manifestSourceRev !== null &&
    sceneRev !== null &&
    manifestSourceRev > sceneRev
  ) {
    return {
      evidence: "legacy-revision",
      presence: "present",
      reason: "mesh manifest source scene revision is ahead of current scene",
      runAllowed: false,
      state: "inconsistent",
    };
  }

  // 4. Loading state
  if (input.resourceLoadState === "loading") {
    return {
      evidence: "legacy-revision",
      presence: "present",
      reason: "loading required mesh resources",
      runAllowed: false,
      state: "loading",
    };
  }

  // 5. Unknown provenance / transport error
  if (
    input.resourceLoadState === "error" ||
    manifestSourceRev === null ||
    sceneRev === null
  ) {
    return {
      evidence: "legacy-revision",
      presence: "present",
      reason: "mesh provenance or scene revision is incomplete",
      runAllowed: false,
      state: "unknown",
    };
  }

  // 6. Current: exact revision match
  if (manifestSourceRev === sceneRev) {
    return {
      evidence: "legacy-revision",
      presence: "present",
      reason: "mesh manifest source scene revision matches the current scene",
      runAllowed: true,
      state: "current",
    };
  }

  // 7. Stale: manifest source revision is older than current scene
  if (manifestSourceRev < sceneRev) {
    return {
      evidence: "legacy-revision",
      presence: "present",
      reason: "mesh manifest source scene revision is older than the current scene",
      runAllowed: false,
      state: "stale",
    };
  }

  return {
    evidence: "legacy-revision",
    presence: "present",
    reason: "mesh provenance is incomplete",
    runAllowed: false,
    state: "unknown",
  };
}
