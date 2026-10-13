import { describe, expect, it } from "vitest";

import {
  geometryDraftLengthValuesEqual,
  geometryDraftQuantityEquals,
  geometryDraftGeometryEquals,
  geometryDraftTranslationEquals,
  resolveCommittedGeometryObjectDraft,
} from "./objectEditDraftModel";

describe("object edit draft quantity semantics", () => {
  it("treats explicit unit spellings as the same SI geometry and translation values", () => {
    const baseline = resolveCommittedGeometryObjectDraft(
      {
        objects: [{
          geometry: {
            geometry_kind: "Box",
            geometry_params: { size: [1e-7, 1e-7, 1e-8] },
          },
          id: "box",
          transform: { translation: [1e-9, 2e-9, 3e-9] },
        }],
        revision: 4,
      },
      "box",
    );
    expect(baseline).not.toBeNull();
    if (!baseline) return;

    const equivalent = {
      ...baseline,
      size: ["100 nm", "0,1 um", "10 nm"] as [string, string, string],
      translation: ["1 nm", "2 nm", "3 nm"] as [string, string, string],
    };

    expect(geometryDraftGeometryEquals(equivalent, baseline)).toBe(true);
    expect(geometryDraftTranslationEquals(equivalent, baseline)).toBe(true);
    expect(equivalent.size[0]).toBe("100 nm");
  });

  it("uses each field's selected unit for mixed-unit geometry and translation no-ops", () => {
    const baseline = resolveCommittedGeometryObjectDraft(
      {
        objects: [{
          geometry: {
            geometry_kind: "Box",
            geometry_params: { size: [1e-7, 1e-7, 1e-8] },
          },
          id: "box",
          transform: { translation: [1e-9, 2e-9, 3e-9] },
        }],
        revision: 4,
      },
      "box",
    );
    expect(baseline).not.toBeNull();
    if (!baseline) return;

    const equivalent = {
      ...baseline,
      quantityFields: {
        "size.0": { unit: "nm" as const, lastValidSI: 1e-7 },
        "size.1": { unit: "um" as const, lastValidSI: 1e-7 },
        "translation.0": { unit: "nm" as const, lastValidSI: 1e-9 },
        "translation.1": { unit: "um" as const, lastValidSI: 2e-9 },
      },
      size: ["100", "0.1", "1e-8"] as [string, string, string],
      translation: ["1", "0.002", "3e-9"] as [string, string, string],
    };

    expect(geometryDraftGeometryEquals(equivalent, baseline)).toBe(true);
    expect(geometryDraftTranslationEquals(equivalent, baseline)).toBe(true);
    expect(geometryDraftQuantityEquals(equivalent, baseline, "size.1")).toBe(true);
    expect(geometryDraftLengthValuesEqual(1e-7, 1.0000000000000001e-7)).toBe(true);
  });

  it("uses selected units for ArchWaveguide fields including signed z0", () => {
    const baseline = resolveCommittedGeometryObjectDraft(
      {
        objects: [{
          geometry: {
            geometry_kind: "ArchWaveguide",
            geometry_params: {
              arch_height: 5e-8,
              height: 2e-9,
              length: 2.5e-6,
              width: 1e-6,
              z0: -2.5e-8,
            },
          },
          id: "arch",
        }],
        revision: 4,
      },
      "arch",
    );
    expect(baseline).not.toBeNull();
    if (!baseline) return;

    const equivalent = {
      ...baseline,
      quantityFields: {
        length: { unit: "um" as const, lastValidSI: 2.5e-6 },
        width: { unit: "um" as const, lastValidSI: 1e-6 },
        height: { unit: "nm" as const, lastValidSI: 2e-9 },
        archHeight: { unit: "nm" as const, lastValidSI: 5e-8 },
        z0: { unit: "nm" as const, lastValidSI: -2.5e-8 },
      },
      length: "2.5",
      width: "1",
      height: "2",
      archHeight: "50",
      z0: "-25",
    };

    expect(geometryDraftGeometryEquals(equivalent, baseline)).toBe(true);
    expect(geometryDraftQuantityEquals(equivalent, baseline, "z0")).toBe(true);
  });

  it("does not treat invalid or materially different text as a semantic no-op", () => {
    const baseline = resolveCommittedGeometryObjectDraft(
      {
        objects: [{
          geometry: {
            geometry_kind: "Box",
            geometry_params: { size: [1e-7, 1e-7, 1e-8] },
          },
          id: "box",
          transform: { translation: [0, 0, 0] },
        }],
        revision: 4,
      },
      "box",
    );
    expect(baseline).not.toBeNull();
    if (!baseline) return;

    expect(geometryDraftGeometryEquals({
      ...baseline,
      size: ["1e-7", "0.001 nm", "1e-8"],
    }, baseline)).toBe(false);
    expect(geometryDraftTranslationEquals({
      ...baseline,
      translation: ["bad", "0", "0"],
    }, baseline)).toBe(false);
  });
});
