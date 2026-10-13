import type { QuantityUnit } from "./quantityInput";

export type LengthQuantityUnit = Extract<
  QuantityUnit,
  "m" | "mm" | "um" | "µm" | "μm" | "nm"
>;

export type QuantityDraftField =
  | `size.${0 | 1 | 2}`
  | `translation.${0 | 1 | 2}`
  | "radius"
  | "height"
  | "length"
  | "width"
  | "archHeight"
  | "z0";

export interface QuantityDraftFieldMetadata {
  unit: LengthQuantityUnit;
  lastValidSI: number | null;
}

export interface GeometryObjectDraft {
  archHeight: string;
  baseRevision: number | null;
  geometryKind: string;
  height: string;
  length: string;
  material: string;
  mode: "committed" | "draft-new" | "missing";
  name: string;
  notes: string;
  objectId: string;
  radius: string;
  region: string;
  rotation: [string, string, string];
  scale: [string, string, string];
  size: [string, string, string];
  translation: [string, string, string];
  quantityFields?: Partial<Record<QuantityDraftField, QuantityDraftFieldMetadata>>;
  width: string;
  z0: string;
}

export interface ObjectEditSessionTarget {
  objectId: string;
  sessionScopeKey: string | null;
  targetKey: string;
}

export interface ObjectEditSessionIdentity extends ObjectEditSessionTarget {
  draftId: string;
  epoch: number;
}

export interface ObjectEditSessionSnapshot<TDraft> {
  applyOperationId: number | null;
  dirty: boolean;
  draft: TDraft | null;
  editVersion: number;
  identity: ObjectEditSessionIdentity | null;
}

export interface ObjectEditApplyOperation<TDraft> {
  id: number;
  identity: ObjectEditSessionIdentity;
  submittedDraft: TDraft;
  submittedVersion: number;
}
