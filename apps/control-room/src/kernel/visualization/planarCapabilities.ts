export interface FieldMapCapability {
  enabled: boolean;
  reasonCode: string | null;
}

export interface PlanarMeshOverlayDescriptor {
  available: boolean;
  boundaryClassification: string;
  codec: string | null | undefined;
  geometrySource?: string | null;
}

export interface PlanarInspectorCapabilities {
  boundaries: FieldMapCapability;
  bounds: FieldMapCapability;
  contours: FieldMapCapability;
  mesh: FieldMapCapability;
  points: FieldMapCapability;
  raster: FieldMapCapability;
  vectors: FieldMapCapability;
}

export type PlanarScopeKind = "monitor_target" | "mesh_part" | "airbox" | "layer";

/**
 * Structured FDM grids have no mesh parts; native layers exist only for FDM
 * multilayer carriers. The Airbox scope is resolved by the backend carrier
 * (FDM Airbox cells or FEM airbox elements) and fails there with its exact reason.
 */
export function planarScopeCapability(input: {
  discretization: string | null | undefined;
  scopeKind: PlanarScopeKind;
}): FieldMapCapability {
  const discretization = input.discretization?.trim().toLowerCase();
  if (discretization === "fdm" && input.scopeKind === "mesh_part") {
    return { enabled: false, reasonCode: "fdm_scope_not_supported" };
  }
  if (discretization === "fem" && input.scopeKind === "layer") {
    return { enabled: false, reasonCode: "fem_layer_scope_not_supported" };
  }
  return { enabled: true, reasonCode: null };
}

export function resolveFieldMapCapabilities(input: {
  meshOverlayAvailable: boolean;
  spatial: boolean;
  vectorComponents: number;
}) {
  const unsupported = (reasonCode: string): FieldMapCapability => ({
    enabled: false,
    reasonCode,
  });
  return {
    contours: input.spatial
      ? { enabled: true, reasonCode: null }
      : unsupported("quantity_not_spatial"),
    mesh: input.meshOverlayAvailable
      ? { enabled: true, reasonCode: null }
      : unsupported("mesh_overlay_unavailable"),
    vectors:
      input.spatial && input.vectorComponents >= 2
        ? { enabled: true, reasonCode: null }
        : unsupported(
            input.spatial ? "quantity_not_vector" : "quantity_not_spatial",
          ),
  };
}

/** Keeps Field Map and the Inspector on one fail-closed capability vocabulary. */
export function resolvePlanarInspectorCapabilities(input: {
  descriptor: PlanarMeshOverlayDescriptor | null | undefined;
  discretization: string | null | undefined;
  metaAvailable?: boolean;
  occupancyAvailable?: boolean;
  quantity: {
    available: boolean;
    components: number;
    location?: string | null;
  } | null | undefined;
  scopeKind: PlanarScopeKind;
}): PlanarInspectorCapabilities {
  const quantityAvailable = input.quantity?.available === true;
  const spatial =
    quantityAvailable &&
    input.quantity?.location?.trim().toLowerCase() !== "global";
  const scope = planarScopeCapability({
    discretization: input.discretization,
    scopeKind: input.scopeKind,
  });
  const descriptor = input.descriptor;
  const meshOverlayAvailable =
    spatial &&
    scope.enabled &&
    descriptor?.available === true &&
    (descriptor.codec === "fmcs.v4" ||
      (descriptor.codec === "fmfg.v1" && descriptor.geometrySource === "fdm_structured_grid"));
  const base = resolveFieldMapCapabilities({
    meshOverlayAvailable,
    spatial: spatial && scope.enabled,
    vectorComponents: input.quantity?.components ?? 0,
  });
  const metaAvailable = input.metaAvailable ?? false;
  const bounds = spatial && scope.enabled && metaAvailable
    ? { enabled: true, reasonCode: null }
    : {
        enabled: false,
        reasonCode: !scope.enabled
          ? scope.reasonCode
          : !spatial
            ? "quantity_not_spatial"
            : "planar_meta_unavailable",
      };
  const points = spatial && scope.enabled && metaAvailable && input.occupancyAvailable === true
    ? { enabled: true, reasonCode: null }
    : {
        enabled: false,
        reasonCode: !scope.enabled
          ? scope.reasonCode
          : !spatial
            ? "quantity_not_spatial"
            : !metaAvailable
              ? "planar_meta_unavailable"
              : "occupancy_mask_unavailable",
      };
  const boundaries =
    meshOverlayAvailable && descriptor?.boundaryClassification === "exact"
      ? { enabled: true, reasonCode: null }
      : {
          enabled: false,
          reasonCode: !scope.enabled
            ? scope.reasonCode
            : !spatial
              ? "quantity_not_spatial"
              : !descriptor?.available
                ? "mesh_overlay_unavailable"
                : descriptor.codec === "fmfg.v1"
                  ? "target_boundaries_unavailable"
                  : descriptor.codec !== "fmcs.v4"
                    ? "mesh_overlay_codec_unsupported"
                    : "boundaries_not_exact",
        };

  return {
    boundaries,
    bounds,
    contours: base.contours,
    mesh: base.mesh,
    points,
    raster: base.contours,
    vectors: base.vectors,
  };
}
