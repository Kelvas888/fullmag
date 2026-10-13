import type {
  GeometryObjectDraft,
  LengthQuantityUnit,
  QuantityDraftField,
  QuantityDraftFieldMetadata,
} from "./objectEditTypes";
import {
  changeQuantityInputUnit,
  parseQuantityInput,
  type QuantityInputState,
  type QuantityUnitChangeResult,
} from "./quantityInput";

export const QUANTITY_DRAFT_FIELDS = [
  "size.0",
  "size.1",
  "size.2",
  "translation.0",
  "translation.1",
  "translation.2",
  "radius",
  "height",
  "length",
  "width",
  "archHeight",
  "z0",
] as const satisfies readonly QuantityDraftField[];

const DEFAULT_LENGTH_UNIT: LengthQuantityUnit = "m";

type QuantityDraftVector = "size" | "translation";
type QuantityDraftScalar = Exclude<
  QuantityDraftField,
  `size.${number}` | `translation.${number}`
>;
type VectorAddress = { field: QuantityDraftVector; index: 0 | 1 | 2 };

function vectorAddress(field: QuantityDraftField): VectorAddress | null {
  const separator = field.indexOf(".");
  if (separator < 0) return null;
  const vector = field.slice(0, separator);
  const axis = field.slice(separator + 1);
  const index: VectorAddress["index"] | null =
    axis === "0" ? 0 : axis === "1" ? 1 : axis === "2" ? 2 : null;
  if (
    (vector !== "size" && vector !== "translation") ||
    index === null
  ) return null;
  return { field: vector, index };
}

function fieldMetadata(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
): QuantityDraftFieldMetadata | undefined {
  return draft.quantityFields?.[field];
}

function finiteSI(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function requiresPositiveValue(field: QuantityDraftField): boolean {
  return field.startsWith("size.") ||
    field === "radius" ||
    field === "height" ||
    field === "length" ||
    field === "width" ||
    field === "archHeight";
}

function hasValidDomainValue(field: QuantityDraftField, value: number | null): value is number {
  return value !== null && Number.isFinite(value) &&
    (!requiresPositiveValue(field) || value > 0);
}

function withFieldMetadata(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
  metadata: QuantityDraftFieldMetadata | undefined,
): GeometryObjectDraft {
  const quantityFields = { ...draft.quantityFields };
  if (metadata) quantityFields[field] = metadata;
  else delete quantityFields[field];

  const nextDraft: GeometryObjectDraft = { ...draft, quantityFields };
  if (Object.keys(quantityFields).length === 0) delete nextDraft.quantityFields;
  return nextDraft;
}

/** Returns the raw editor text for one scalar or vector-axis quantity field. */
export function getRawQuantityField(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
): string {
  const address = vectorAddress(field);
  if (address?.field === "size") return draft.size[address.index];
  if (address?.field === "translation") return draft.translation[address.index];
  return draft[field as QuantityDraftScalar];
}

/** Copies a draft while replacing only one raw scalar or vector-axis value. */
export function setRawQuantityField(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
  rawText: string,
): GeometryObjectDraft {
  const address = vectorAddress(field);
  if (address?.field === "size") {
    const size: GeometryObjectDraft["size"] = [...draft.size];
    size[address.index] = rawText;
    return { ...draft, size };
  }
  if (address?.field === "translation") {
    const translation: GeometryObjectDraft["translation"] = [...draft.translation];
    translation[address.index] = rawText;
    return { ...draft, translation };
  }
  return { ...draft, [field as QuantityDraftScalar]: rawText };
}

/** Parses raw text with the field's selected unit and stored last-valid value. */
export function parseDraftQuantityField(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
): QuantityInputState {
  const metadata = fieldMetadata(draft, field);
  const previousLastValidSI = finiteSI(metadata?.lastValidSI);
  const parsed = parseQuantityInput(
    getRawQuantityField(draft, field),
    "length",
    metadata?.unit ?? DEFAULT_LENGTH_UNIT,
    previousLastValidSI,
  );
  if (
    parsed.parseStatus !== "valid" ||
    hasValidDomainValue(field, parsed.parsedSI)
  ) return parsed;

  return {
    ...parsed,
    lastValidSI: previousLastValidSI,
    parseStatus: "invalid",
    parsedSI: null,
  };
}

/**
 * Keeps the user's raw text and changes lastValidSI only for a valid,
 * domain-accepted value. An implicit meter unit is not materialized unless a
 * field needs metadata to retain its selected unit or a last-valid preview.
 */
export function updateRawQuantityField(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
  rawText: string,
): GeometryObjectDraft {
  const existingMetadata = fieldMetadata(draft, field);
  const unit = existingMetadata?.unit ?? DEFAULT_LENGTH_UNIT;
  const currentParsed = parseDraftQuantityField(draft, field);
  const previousLastValidSI = currentParsed.parseStatus === "valid"
    ? finiteSI(currentParsed.parsedSI)
    : finiteSI(existingMetadata?.lastValidSI) ?? finiteSI(currentParsed.lastValidSI);
  const nextDraft = setRawQuantityField(draft, field, rawText);
  const parsed = parseQuantityInput(rawText, "length", unit, previousLastValidSI);
  const accepted = parsed.parseStatus === "valid" &&
    hasValidDomainValue(field, parsed.parsedSI);
  const lastValidSI = accepted
    ? parsed.parsedSI
    : previousLastValidSI;
  const shouldStoreMetadata = existingMetadata !== undefined ||
    unit !== DEFAULT_LENGTH_UNIT ||
    (!accepted && lastValidSI !== null);
  return withFieldMetadata(
    nextDraft,
    field,
    shouldStoreMetadata ? { unit, lastValidSI } : undefined,
  );
}

/** Writes a canonical SI value without changing the editor's selected unit. */
export function updateQuantityFieldSI(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
  value: number,
): GeometryObjectDraft {
  const unit = fieldMetadata(draft, field)?.unit ?? DEFAULT_LENGTH_UNIT;
  const input = parseQuantityInput(String(value), "length", "m");
  const converted = changeQuantityInputUnit(input, unit);
  return updateRawQuantityField(draft, field,
    converted.ok ? converted.input.rawText : `${String(value)} m`);
}

export type DraftQuantityUnitChangeResult =
  | { ok: true; draft: GeometryObjectDraft }
  | {
      ok: false;
      draft: GeometryObjectDraft;
      reason: Extract<QuantityUnitChangeResult, { ok: false }>["reason"];
    };

/**
 * Atomically rewrites one valid field in a new display unit. Invalid or
 * incomplete raw values block only this field and return the original draft.
 */
export function changeDraftQuantityUnit(
  draft: GeometryObjectDraft,
  field: QuantityDraftField,
  nextUnit: LengthQuantityUnit,
): DraftQuantityUnitChangeResult {
  const input = parseDraftQuantityField(draft, field);
  const changed = changeQuantityInputUnit(input, nextUnit);
  if (!changed.ok) return { ok: false, draft, reason: changed.reason };

  const nextDraft = setRawQuantityField(draft, field, changed.input.rawText);
  return {
    ok: true,
    draft: withFieldMetadata(nextDraft, field, {
      unit: nextUnit,
      lastValidSI: finiteSI(changed.input.lastValidSI),
    }),
  };
}

/**
 * Formats canonical SI values in each current field's selected unit while
 * preserving the current unit metadata and refreshing valid last-valid SI.
 */
export function canonicalDraftInSelectedUnits(
  canonical: GeometryObjectDraft,
  current: GeometryObjectDraft,
): GeometryObjectDraft {
  const nextQuantityFields: Partial<
    Record<QuantityDraftField, QuantityDraftFieldMetadata>
  > = {};
  let nextDraft: GeometryObjectDraft = { ...canonical };
  delete nextDraft.quantityFields;

  for (const field of QUANTITY_DRAFT_FIELDS) {
    const currentMetadata = fieldMetadata(current, field);
    const unit = currentMetadata?.unit ?? DEFAULT_LENGTH_UNIT;
    const canonicalRaw = getRawQuantityField(canonical, field);
    const canonicalInput = parseQuantityInput(canonicalRaw, "length", "m");
    const canonicalSI = canonicalInput.parsedSI;
    let formattedRaw = canonicalRaw;

    if (canonicalInput.parseStatus === "valid" && canonicalSI !== null) {
      const converted = changeQuantityInputUnit(canonicalInput, unit);
      formattedRaw = converted.ok
        ? converted.input.rawText
        : `${String(canonicalSI)} m`;
      nextDraft = setRawQuantityField(nextDraft, field, formattedRaw);

      const lastValidSI = hasValidDomainValue(field, canonicalSI)
        ? canonicalSI
        : finiteSI(currentMetadata?.lastValidSI);
      if (currentMetadata || unit !== DEFAULT_LENGTH_UNIT) {
        nextQuantityFields[field] = { unit, lastValidSI };
      }
    } else {
      // Canonical drafts are expected to be finite SI values. If one is
      // malformed, keep its text rather than reinterpret it in a display unit.
      nextDraft = setRawQuantityField(nextDraft, field, canonicalRaw);
      if (currentMetadata) nextQuantityFields[field] = currentMetadata;
    }
  }

  if (Object.keys(nextQuantityFields).length > 0) {
    nextDraft.quantityFields = nextQuantityFields;
  }
  return nextDraft;
}
