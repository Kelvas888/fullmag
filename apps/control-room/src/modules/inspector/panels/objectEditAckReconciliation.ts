import type { GeometryObjectDraft } from "@/kernel/authoring/object-edit/objectEditTypes";

import {
  geometryDraftGeometryEquals,
  geometryDraftTranslationEquals,
} from "./geometryObjectPanelModel";

const GEOMETRY_FIELDS = [
  "archHeight", "geometryKind", "height", "length", "radius", "width", "z0",
] as const satisfies readonly (keyof GeometryObjectDraft)[];
const METADATA_FIELDS = ["name", "notes", "material", "region"] as const;

function normalizedReference(value: string): string | null {
  const trimmed = value.trim();
  return !trimmed || trimmed === "unassigned" ? null : trimmed;
}

export function objectEditMetadataEquals(left: GeometryObjectDraft, right: GeometryObjectDraft): boolean {
  return left.name === right.name && left.notes === right.notes &&
    normalizedReference(left.material) === normalizedReference(right.material) &&
    normalizedReference(left.region) === normalizedReference(right.region);
}

function rebaseGeometry(current: GeometryObjectDraft, baseline: GeometryObjectDraft, draft: GeometryObjectDraft): void {
  for (const field of GEOMETRY_FIELDS) {
    if (!Object.is(current[field], baseline[field])) Object.assign(draft, { [field]: current[field] });
  }
  for (const field of ["size", "translation"] as const) {
    const rebased: [string, string, string] = [...draft[field]];
    for (const index of [0, 1, 2] as const) {
      if (!Object.is(current[field][index], baseline[field][index])) rebased[index] = current[field][index];
    }
    Object.assign(draft, { [field]: rebased });
  }
}

function rebaseMetadata(current: GeometryObjectDraft, submitted: GeometryObjectDraft, draft: GeometryObjectDraft): void {
  for (const field of METADATA_FIELDS) {
    if (!Object.is(current[field], submitted[field])) Object.assign(draft, { [field]: current[field] });
  }
}

function reconciled(draft: GeometryObjectDraft, canonical: GeometryObjectDraft): { dirty: boolean; draft: GeometryObjectDraft } {
  return {
    dirty: !geometryDraftGeometryEquals(draft, canonical) ||
      !geometryDraftTranslationEquals(draft, canonical) || !objectEditMetadataEquals(draft, canonical),
    draft,
  };
}

/** Retain post-submit raw edits; immutable identity and revision always come from ACK. */
export function reconcileObjectEditAck(
  current: GeometryObjectDraft,
  submitted: GeometryObjectDraft,
  canonical: GeometryObjectDraft,
): { dirty: boolean; draft: GeometryObjectDraft } {
  const draft = { ...canonical };
  rebaseGeometry(current, submitted, draft);
  rebaseMetadata(current, submitted, draft);
  // R1 exposes translation only; disabled rotation and scale remain canonical.
  return reconciled(draft, canonical);
}

/** Identity writes leave all unsent geometry edits intact as well as newer metadata. */
export function reconcileObjectIdentityAck(
  current: GeometryObjectDraft,
  submitted: GeometryObjectDraft,
  baseline: GeometryObjectDraft,
  canonical: GeometryObjectDraft,
): { dirty: boolean; draft: GeometryObjectDraft } {
  const draft = { ...canonical };
  rebaseGeometry(current, baseline, draft);
  rebaseMetadata(current, submitted, draft);
  return reconciled(draft, canonical);
}
