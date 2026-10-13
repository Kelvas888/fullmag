import { describe, expect, it } from "vitest";

import type { GeometryObjectDraft, LengthQuantityUnit } from "./objectEditTypes";
import {
  canonicalDraftInSelectedUnits,
  changeDraftQuantityUnit,
  getRawQuantityField,
  parseDraftQuantityField,
  setRawQuantityField,
  updateRawQuantityField,
  updateQuantityFieldSI,
} from "./quantityDraftFields";

function draft(overrides: Partial<GeometryObjectDraft> = {}): GeometryObjectDraft {
  return {
    archHeight: "5e-8",
    baseRevision: 10,
    geometryKind: "Box",
    height: "1e-8",
    length: "1e-6",
    material: "unassigned",
    mode: "committed",
    name: "Magnet",
    notes: "",
    objectId: "magnet-a",
    radius: "5e-8",
    region: "unassigned",
    rotation: ["0", "0", "0"],
    scale: ["1", "1", "1"],
    size: ["1e-7", "1e-7", "1e-8"],
    translation: ["0", "0", "0"],
    width: "1e-6",
    z0: "0",
    ...overrides,
  };
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach((child) => deepFreeze(child));
  }
  return value;
}

describe("quantityDraftFields", () => {
  it("round-trips 100 nm, 0.1 um, and 1e-7 m through SI", () => {
    const nanometerDraft = draft({
      quantityFields: {
        "size.0": { unit: "nm", lastValidSI: 1e-7 },
      },
      size: ["100", "1e-7", "1e-8"],
    });

    expect(parseDraftQuantityField(nanometerDraft, "size.0").parsedSI).toBeCloseTo(1e-7, 22);
    const micrometerChange = changeDraftQuantityUnit(nanometerDraft, "size.0", "um");
    expect(micrometerChange.ok).toBe(true);
    if (!micrometerChange.ok) return;
    expect(Number(getRawQuantityField(micrometerChange.draft, "size.0"))).toBeCloseTo(0.1, 14);
    expect(parseDraftQuantityField(micrometerChange.draft, "size.0").parsedSI).toBeCloseTo(1e-7, 22);

    const meterChange = changeDraftQuantityUnit(micrometerChange.draft, "size.0", "m");
    expect(meterChange.ok).toBe(true);
    if (!meterChange.ok) return;
    expect(Number(getRawQuantityField(meterChange.draft, "size.0"))).toBeCloseTo(1e-7, 22);
    expect(parseDraftQuantityField(meterChange.draft, "size.0").parsedSI).toBeCloseTo(1e-7, 22);
  });

  it("stages gesture SI in the translation axis's selected unit", () => {
    const original = draft({ translation: ["20", "0", "0"], quantityFields: {
      "translation.0": { unit: "nm", lastValidSI: 20e-9 },
    } });
    const moved = updateQuantityFieldSI(original, "translation.0", 35e-9);
    expect(Number(moved.translation[0])).toBeCloseTo(35, 12);
    expect(moved.quantityFields?.["translation.0"]?.unit).toBe("nm");
    expect(parseDraftQuantityField(moved, "translation.0").parsedSI).toBeCloseTo(35e-9, 22);
    expect(original.translation[0]).toBe("20");
  });

  it("changes only the selected field's unit and raw representation", () => {
    const original = draft({
      quantityFields: {
        "size.0": { unit: "nm", lastValidSI: 1e-7 },
        "size.1": { unit: "mm", lastValidSI: 1e-7 },
      },
      size: ["100", "0.0001", "1e-8"],
    });
    const result = changeDraftQuantityUnit(original, "size.0", "um");

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.draft.quantityFields?.["size.0"]?.unit).toBe("um");
    expect(result.draft.quantityFields?.["size.0"]?.lastValidSI).toBeCloseTo(1e-7, 22);
    expect(result.draft.quantityFields?.["size.1"]).toEqual({
      unit: "mm",
      lastValidSI: 1e-7,
    });
    expect(result.draft.size[1]).toBe(original.size[1]);
    expect(parseDraftQuantityField(result.draft, "size.0").parsedSI).toBeCloseTo(1e-7, 22);
  });

  it("retains invalid raw text and the last valid SI value", () => {
    const original = draft({
      quantityFields: {
        "size.0": { unit: "nm", lastValidSI: 1e-7 },
      },
      size: ["100", "1e-7", "1e-8"],
    });
    const updated = updateRawQuantityField(original, "size.0", "1e-");

    expect(getRawQuantityField(updated, "size.0")).toBe("1e-");
    expect(updated.quantityFields?.["size.0"]).toEqual({
      unit: "nm",
      lastValidSI: parseDraftQuantityField(original, "size.0").parsedSI,
    });
    expect(parseDraftQuantityField(updated, "size.0")).toMatchObject({
      lastValidSI: parseDraftQuantityField(original, "size.0").parsedSI,
      parsedSI: null,
      parseStatus: "incomplete",
      rawText: "1e-",
    });

    const invalidDomain = updateRawQuantityField(updated, "size.0", "0");
    expect(getRawQuantityField(invalidDomain, "size.0")).toBe("0");
    expect(invalidDomain.quantityFields?.["size.0"]?.lastValidSI).toBe(parseDraftQuantityField(original, "size.0").parsedSI);
    expect(parseDraftQuantityField(invalidDomain, "size.0")).toMatchObject({
      lastValidSI: parseDraftQuantityField(original, "size.0").parsedSI,
      parsedSI: null,
      parseStatus: "invalid",
    });
  });

  it("accepts any finite translation and z0 while dimensions must be positive", () => {
    const original = draft({
      quantityFields: {
        "translation.2": { unit: "mm", lastValidSI: 0 },
        z0: { unit: "um", lastValidSI: 0 },
      },
    });
    const translated = updateRawQuantityField(original, "translation.2", "-2");
    const z0 = updateRawQuantityField(translated, "z0", "-3");
    const zeroDimension = updateRawQuantityField(z0, "radius", "0");

    expect(parseDraftQuantityField(z0, "translation.2")).toMatchObject({
      parsedSI: -2e-3,
      parseStatus: "valid",
    });
    expect(z0.quantityFields?.z0?.lastValidSI).toBe(-3e-6);
    expect(parseDraftQuantityField(z0, "z0")).toMatchObject({
      parsedSI: -3e-6,
      parseStatus: "valid",
    });
    expect(parseDraftQuantityField(zeroDimension, "radius")).toMatchObject({
      parsedSI: null,
      parseStatus: "invalid",
    });
  });

  it("blocks a wrong-dimension unit without changing the draft", () => {
    const original = draft({
      quantityFields: {
        "size.0": { unit: "nm", lastValidSI: 1e-7 },
      },
      size: ["100", "1e-7", "1e-8"],
    });
    const result = changeDraftQuantityUnit(
      original,
      "size.0",
      "rad" as LengthQuantityUnit,
    );

    expect(result).toEqual({ ok: false, draft: original, reason: "invalid-unit" });
  });

  it("blocks incomplete fields and unit conversions that overflow", () => {
    const incomplete = draft({
      quantityFields: {
        "size.0": { unit: "nm", lastValidSI: 1e-7 },
      },
      size: ["-", "1e-7", "1e-8"],
    });
    expect(changeDraftQuantityUnit(incomplete, "size.0", "um")).toMatchObject({
      ok: false,
      reason: "incomplete",
    });

    const huge = draft({
      quantityFields: {
        "size.0": { unit: "m", lastValidSI: Number.MAX_VALUE },
      },
      size: [String(Number.MAX_VALUE), "1e-7", "1e-8"],
    });
    expect(changeDraftQuantityUnit(huge, "size.0", "nm")).toMatchObject({
      ok: false,
      reason: "out-of-range",
      draft: huge,
    });
  });

  it("formats canonical ACK values in the current selected units without mutation", () => {
    const current = deepFreeze(draft({
      quantityFields: {
        "size.0": { unit: "nm", lastValidSI: 1e-7 },
        "translation.0": { unit: "um", lastValidSI: 1e-6 },
        radius: { unit: "mm", lastValidSI: 5e-8 },
      },
      size: ["100", "1e-7", "1e-8"],
    }));
    const canonical = deepFreeze(draft({
      radius: "4e-3",
      size: ["2e-7", "1e-7", "1e-8"],
      translation: ["-3e-6", "0", "0"],
    }));
    const currentBefore = JSON.stringify(current);
    const canonicalBefore = JSON.stringify(canonical);
    const ackDraft = canonicalDraftInSelectedUnits(canonical, current);

    expect(Number(ackDraft.size[0])).toBeCloseTo(200, 12);
    expect(ackDraft.quantityFields?.["size.0"]).toEqual({
      unit: "nm",
      lastValidSI: 2e-7,
    });
    expect(ackDraft.translation[0]).toBe("-3");
    expect(ackDraft.quantityFields?.["translation.0"]).toEqual({
      unit: "um",
      lastValidSI: -3e-6,
    });
    expect(ackDraft.radius).toBe("4");
    expect(ackDraft.quantityFields?.radius).toEqual({
      unit: "mm",
      lastValidSI: 4e-3,
    });
    expect(ackDraft.quantityFields?.height).toBeUndefined();
    expect(parseDraftQuantityField(ackDraft, "size.0").parsedSI).toBeCloseTo(2e-7, 22);
    expect(JSON.stringify(current)).toBe(currentBefore);
    expect(JSON.stringify(canonical)).toBe(canonicalBefore);
  });

  it("copies raw setters and field updates instead of mutating shared draft arrays", () => {
    const original = deepFreeze(draft({
      quantityFields: {
        "size.0": { unit: "nm", lastValidSI: 1e-7 },
      },
      size: ["100", "1e-7", "1e-8"],
    }));
    const originalSize = original.size;
    const rawUpdated = setRawQuantityField(original, "size.1", "2");
    const quantityUpdated = updateRawQuantityField(original, "size.0", "200");

    expect(original.size).toEqual(["100", "1e-7", "1e-8"]);
    expect(rawUpdated).not.toBe(original);
    expect(rawUpdated.size).not.toBe(originalSize);
    expect(rawUpdated.size).toEqual(["100", "2", "1e-8"]);
    expect(quantityUpdated.size).toEqual(["200", "1e-7", "1e-8"]);
    expect(original.quantityFields?.["size.0"]?.lastValidSI).toBe(1e-7);
  });
});
