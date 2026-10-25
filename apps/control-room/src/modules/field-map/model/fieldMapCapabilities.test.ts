import { describe, expect, it } from "vitest";

import {
  resolveFieldMapCapabilities,
  resolvePlanarInspectorCapabilities,
} from "./fieldMapCapabilities";

describe("field-map capabilities", () => {
  it("returns stable reasons instead of enabled controls that do nothing", () => {
    expect(
      resolveFieldMapCapabilities({
        meshOverlayAvailable: false,
        spatial: false,
        vectorComponents: 0,
      }),
    ).toEqual({
      contours: { enabled: false, reasonCode: "quantity_not_spatial" },
      mesh: { enabled: false, reasonCode: "mesh_overlay_unavailable" },
      vectors: { enabled: false, reasonCode: "quantity_not_spatial" },
    });
  });
});

describe("planar inspector capabilities", () => {
  const quantity = { available: true, components: 3, location: "node" };

  it.each([
    ["exact", { available: true, boundaryClassification: "exact", codec: "fmcs.v4" }, "fem", { kind: "monitor_target" as const }, true, true, true],
    ["degraded", { available: true, boundaryClassification: "degraded_v3", codec: "fmcs.v4" }, "fem", { kind: "monitor_target" as const }, true, false, true],
    ["unavailable", { available: false, boundaryClassification: "exact", codec: "fmcs.v4" }, "fem", { kind: "monitor_target" as const }, false, false, true],
    ["wrong codec", { available: true, boundaryClassification: "exact", codec: "fmcs.v3" }, "fem", { kind: "monitor_target" as const }, false, false, true],
    ["FDM mesh part", { available: true, boundaryClassification: "exact", codec: "fmcs.v4" }, "fdm", { kind: "mesh_part" as const }, false, false, false],
    ["FDM structured grid", { available: true, boundaryClassification: "unavailable", codec: "fmfg.v1", geometrySource: "fdm_structured_grid" }, "fdm", { kind: "monitor_target" as const }, true, false, true],
  ] as const)("fails closed for %s descriptors and scope", (_name, descriptor, discretization, scope, mesh, boundaries, raster) => {
    const result = resolvePlanarInspectorCapabilities({
      descriptor,
      discretization,
      metaAvailable: true,
      occupancyAvailable: true,
      quantity,
      scopeKind: scope.kind,
    });

    expect(result.mesh.enabled).toBe(mesh);
    expect(result.boundaries.enabled).toBe(boundaries);
    expect(result.bounds.enabled).toBe(raster);
    expect(result.points.enabled).toBe(raster);
    expect(result.raster.enabled).toBe(raster);
  });

  it("fails closed for points until canonical metadata and occupancy are materialized", () => {
    const input = {
      descriptor: { available: true, boundaryClassification: "exact", codec: "fmcs.v4" },
      discretization: "fem",
      quantity,
      scopeKind: "monitor_target" as const,
    };
    expect(resolvePlanarInspectorCapabilities(input).points).toEqual({
      enabled: false,
      reasonCode: "planar_meta_unavailable",
    });
    expect(resolvePlanarInspectorCapabilities({ ...input, metaAvailable: true }).points).toEqual({
      enabled: false,
      reasonCode: "occupancy_mask_unavailable",
    });
    expect(resolvePlanarInspectorCapabilities({ ...input, metaAvailable: true }).bounds.enabled).toBe(true);
  });

  it("disables vectors for a scalar spatial quantity with a stable reason", () => {
    expect(
      resolvePlanarInspectorCapabilities({
        descriptor: { available: true, boundaryClassification: "exact", codec: "fmcs.v4" },
        discretization: "fem",
        metaAvailable: true,
        occupancyAvailable: true,
        quantity: { available: true, components: 1, location: "cell" },
        scopeKind: "monitor_target",
      }).vectors,
    ).toEqual({ enabled: false, reasonCode: "quantity_not_vector" });
  });
});

describe("planar tensor projection admission", () => {
  const tensor = {
    rank: 2, shape: [3, 3], layout: "flow_major", axes: ["flow", "spin"],
    component_labels: ["Q_xx", "Q_xy", "Q_xz", "Q_yx", "Q_yy", "Q_yz", "Q_zx", "Q_zy", "Q_zz"],
  };
  const input = {
    descriptor: { available: true, boundaryClassification: "exact", codec: "fmcs.v4" },
    discretization: "fem", metaAvailable: true, occupancyAvailable: true,
    quantity: { available: true, components: 9, location: "node" },
    scopeKind: "monitor_target" as const,
    tensor,
  };

  it.each([1, 2, 3])("preserves ordinary %i-component fields", (components) => {
    const result = resolvePlanarInspectorCapabilities({
      ...input, tensor: null, quantity: { ...input.quantity, components },
    });
    expect(result.raster.enabled).toBe(true);
    expect(result.vectors.enabled).toBe(components > 1);
  });

  it.each([0, 4, 6, 9, 12, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects unsupported raw shape %s without disabling geometry", (components) => {
      const result = resolveFieldMapCapabilities({
        meshOverlayAvailable: true, spatial: true, vectorComponents: components,
      });
      expect(result.contours).toEqual({ enabled: false, reasonCode: "quantity_shape_unsupported" });
      expect(result.vectors.enabled).toBe(false);
      expect(result.mesh.enabled).toBe(true);
    },
  );

  it.each(["c0", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "frobenius"])(
    "admits explicit scalar projection %s without vector glyphs", (component) => {
      const result = resolvePlanarInspectorCapabilities({ ...input, component });
      expect(result.raster.enabled).toBe(true);
      expect(result.vectors).toEqual({ enabled: false, reasonCode: "quantity_not_vector" });
    },
  );

  it.each(["spin_flow_x", "spin_flow_y", "spin_flow_z"])(
    "admits explicit spatial flow vector %s", (component) => {
      const result = resolvePlanarInspectorCapabilities({ ...input, component });
      expect(result.raster.enabled).toBe(true);
      expect(result.vectors.enabled).toBe(true);
    },
  );

  it.each([null, undefined, "full", "magnitude", "x", "c9", "spin_flow_w"])(
    "rejects missing or invalid tensor projection %s", (component) => {
      const result = resolvePlanarInspectorCapabilities({ ...input, component });
      expect(result.raster.enabled).toBe(false);
      expect(result.vectors.enabled).toBe(false);
      expect(result.mesh.enabled).toBe(true);
      expect(result.bounds.enabled).toBe(true);
    },
  );

  it.each([
    null,
    { ...tensor, rank: 1 },
    { ...tensor, shape: [3, 2] },
    { ...tensor, layout: "spin_major" },
    { ...tensor, axes: ["spin", "flow"] },
    { ...tensor, component_labels: tensor.component_labels.slice(1) },
    { ...tensor, component_labels: ["", ...tensor.component_labels.slice(1)] },
  ])("rejects absent or malformed canonical descriptor %#", (descriptor) => {
    const result = resolvePlanarInspectorCapabilities({ ...input, tensor: descriptor, component: "spin_flow_y" });
    expect(result.raster.enabled).toBe(false);
    expect(result.vectors.enabled).toBe(false);
  });

  it.each([1, 3, 8, 10])("rejects descriptor/carrier mismatch with %i components", (components) => {
    const result = resolvePlanarInspectorCapabilities({
      ...input, component: "spin_flow_y", quantity: { ...input.quantity, components },
    });
    expect(result.raster.enabled).toBe(false);
    expect(result.vectors.enabled).toBe(false);
  });

  it("rejects raw nine-component fields without canonical metadata or projection", () => {
    const result = resolvePlanarInspectorCapabilities({ ...input, tensor: null });
    expect(result.raster.enabled).toBe(false);
    expect(result.vectors.enabled).toBe(false);
  });
});
