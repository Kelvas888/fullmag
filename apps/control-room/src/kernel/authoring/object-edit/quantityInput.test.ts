import { describe, expect, it } from "vitest";

import {
  changeQuantityInputUnit,
  defaultQuantityUnit,
  parseQuantityInput,
} from "./quantityInput";

describe("parseQuantityInput", () => {
  it.each([
    ["1", 1],
    ["+1.25", 1.25],
    ["-.5", -0.5],
    ["1,25", 1.25],
    ["1e-7", 1e-7],
    ["100 nm", 1e-7],
    ["0,1 um", 1e-7],
    ["1e-7 m", 1e-7],
  ] as const)("parses a length scalar %s into SI", (rawText, parsedSI) => {
    expect(parseQuantityInput(rawText, "length", "m")).toMatchObject({
      dimension: "length",
      lastValidSI: parsedSI,
      parsedSI,
      parseStatus: "valid",
      rawText,
      unit: "m",
    });
  });

  it.each([
    ["1 mm", "mm", 1e-3],
    ["1 um", "um", 1e-6],
    ["1 µm", "µm", 1e-6],
    ["1 μm", "μm", 1e-6],
    ["1 nm", "nm", 1e-9],
  ] as const)("accepts the length unit spelling %s", (rawText, unit, parsedSI) => {
    expect(parseQuantityInput(rawText, "length", "m").parsedSI).toBe(parsedSI);
    expect(parseQuantityInput(rawText, "length", unit).parseStatus).toBe("valid");
  });

  it.each([
    ["180 deg", Math.PI],
    ["180°", Math.PI],
    ["3.5 rad", 3.5],
  ] as const)("parses angle input %s into radians", (rawText, parsedSI) => {
    const parsed = parseQuantityInput(rawText, "angle");
    expect(parsed.parseStatus).toBe("valid");
    expect(parsed.unit).toBe("rad");
    expect(parsed.parsedSI).toBeCloseTo(parsedSI, 14);
  });

  it("uses a dimensionless unit without accepting a suffix", () => {
    expect(defaultQuantityUnit("dimensionless")).toBe("1");
    expect(parseQuantityInput("1,25", "dimensionless")).toMatchObject({
      dimension: "dimensionless",
      parsedSI: 1.25,
      parseStatus: "valid",
      unit: "1",
    });
    expect(parseQuantityInput("1 nm", "dimensionless").parseStatus).toBe("invalid");
    expect(parseQuantityInput("- nm", "dimensionless").parseStatus).toBe("invalid");
    expect(parseQuantityInput("nm", "dimensionless").parseStatus).toBe("invalid");
    expect(parseQuantityInput("rad", "length").parseStatus).toBe("invalid");
    expect(parseQuantityInput("mm", "length").parseStatus).toBe("incomplete");
  });

  it.each(["", "   "])("keeps blank input empty (%j)", (rawText) => {
    expect(parseQuantityInput(rawText, "length", "m", 2e-9)).toMatchObject({
      lastValidSI: 2e-9,
      parsedSI: null,
      parseStatus: "empty",
      rawText,
    });
  });

  it.each(["-", "+", ".", ",", "1e", "1e-", "1E+"])(
    "marks partial numeric input %j incomplete",
    (rawText) => {
      expect(parseQuantityInput(rawText, "length").parseStatus).toBe("incomplete");
    },
  );

  it.each([
    "NaN",
    "Infinity",
    "0x10",
    "1+2",
    "1,2.3",
    "1 000",
    "1  cm",
    "1 cm",
    "1e309",
    "1e-9999",
  ])("rejects malformed or non-finite input %j", (rawText) => {
    expect(parseQuantityInput(rawText, "length").parseStatus).toBe("invalid");
  });

  it("accepts one outer-trimmed space before a compatible suffix only", () => {
    expect(parseQuantityInput(" 100 nm ", "length").parsedSI).toBe(1e-7);
    expect(parseQuantityInput("100  nm", "length").parseStatus).toBe("invalid");
    expect(parseQuantityInput("100\tnm", "length").parseStatus).toBe("invalid");
    expect(parseQuantityInput("100 rad", "length").parseStatus).toBe("invalid");
  });

  it("retains lastValidSI while the current raw text is incomplete or invalid", () => {
    expect(parseQuantityInput("1e-", "length", "m", 1e-7)).toMatchObject({
      lastValidSI: 1e-7,
      parsedSI: null,
      parseStatus: "incomplete",
    });
    expect(parseQuantityInput("1 cm", "length", "m", 1e-7)).toMatchObject({
      lastValidSI: 1e-7,
      parsedSI: null,
      parseStatus: "invalid",
    });
  });
});

describe("changeQuantityInputUnit", () => {
  it("rewrites valid input in the new selected unit while preserving its SI value", () => {
    const original = parseQuantityInput("100 nm", "length", "m");
    const changed = changeQuantityInputUnit(original, "mm");

    expect(changed.ok).toBe(true);
    if (!changed.ok) return;
    expect(changed.input).toMatchObject({
      dimension: "length",
      lastValidSI: original.parsedSI,
      parsedSI: original.parsedSI,
      parseStatus: "valid",
      rawText: "0.0001",
      unit: "mm",
    });
    expect(
      parseQuantityInput(changed.input.rawText, "length", changed.input.unit).parsedSI,
    ).toBeCloseTo(original.parsedSI ?? 0, 22);
  });

  it.each([
    ["1e-", "incomplete"],
    ["1 cm", "invalid"],
  ] as const)("blocks a unit change for %s without altering that field", (rawText, reason) => {
    const original = parseQuantityInput(rawText, "length", "m", 1e-7);
    const result = changeQuantityInputUnit(original, "mm");

    expect(result).toEqual({ input: original, ok: false, reason });
  });

  it("allows an empty field to adopt another compatible unit", () => {
    const original = parseQuantityInput("", "length", "m", 1e-7);
    expect(changeQuantityInputUnit(original, "mm")).toEqual({
      input: {
        ...original,
        unit: "mm",
      },
      ok: true,
    });
  });

  it("rejects changing to a unit from another dimension", () => {
    const original = parseQuantityInput("180", "angle", "rad");
    expect(changeQuantityInputUnit(original, "mm")).toEqual({
      input: original,
      ok: false,
      reason: "invalid-unit",
    });
  });

  it("blocks unit conversion when the selected unit would overflow", () => {
    const original = parseQuantityInput(String(Number.MAX_VALUE), "length", "m");
    expect(original.parseStatus).toBe("valid");
    expect(changeQuantityInputUnit(original, "nm")).toEqual({
      input: original,
      ok: false,
      reason: "out-of-range",
    });
  });

});
