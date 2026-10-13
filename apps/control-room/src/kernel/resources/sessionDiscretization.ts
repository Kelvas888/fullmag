export type SessionDiscretization = "fdm" | "fem";

type LaneSelectionProjection = {
  discretization?: unknown;
};

export type SessionDiscretizationCapabilitiesProjection = {
  active_lane?: {
    resolved?: LaneSelectionProjection | null;
  } | null;
  active_lane_discretization?: unknown;
};

export interface SessionDiscretizationStatus {
  capabilities?: SessionDiscretizationCapabilitiesProjection | null;
  domain?: { discretization?: unknown } | null;
  domainDiscretization?: unknown;
}

export function projectFlatActiveLaneDiscretization(
  capabilities: unknown,
): { value: unknown } | null {
  if (!capabilities || typeof capabilities !== "object") return null;
  if (
    !Object.prototype.hasOwnProperty.call(
      capabilities,
      "active_lane_discretization",
    )
  ) {
    return null;
  }
  return {
    value: (capabilities as { active_lane_discretization?: unknown })
      .active_lane_discretization,
  };
}

export function hasSessionActiveLaneDeclaration(
  status: SessionDiscretizationStatus | null | undefined,
): boolean {
  const capabilities = status?.capabilities;
  return Boolean(
    capabilities &&
      (Object.prototype.hasOwnProperty.call(capabilities, "active_lane") ||
        projectFlatActiveLaneDiscretization(capabilities) !== null),
  );
}

function normalizeDiscretization(value: unknown): SessionDiscretization | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  return normalized === "fdm" || normalized === "fem" ? normalized : null;
}

/**
 * Resolves the live session's solver lane. A present active-lane field is
 * authoritative even when its resolved lane is null or malformed; DomainMeta
 * is only a compatibility source for status payloads that predate active_lane.
 * A flattened lane value is used only when the nested active_lane field is
 * absent from the projected status.
 */
export function resolveSessionDiscretization(
  status: SessionDiscretizationStatus | null | undefined,
): SessionDiscretization | null {
  const capabilities = status?.capabilities;
  if (
    capabilities &&
    Object.prototype.hasOwnProperty.call(capabilities, "active_lane")
  ) {
    return normalizeDiscretization(
      capabilities.active_lane?.resolved?.discretization,
    );
  }
  if (
    capabilities &&
    Object.prototype.hasOwnProperty.call(
      capabilities,
      "active_lane_discretization",
    )
  ) {
    return normalizeDiscretization(capabilities.active_lane_discretization);
  }
  if (
    status?.domain &&
    Object.prototype.hasOwnProperty.call(status.domain, "discretization")
  ) {
    return normalizeDiscretization(status.domain.discretization);
  }
  return normalizeDiscretization(status?.domainDiscretization);
}

export function selectSessionDiscretization(status: {
  data: SessionDiscretizationStatus | null;
}): SessionDiscretization | null {
  return resolveSessionDiscretization(status.data);
}
