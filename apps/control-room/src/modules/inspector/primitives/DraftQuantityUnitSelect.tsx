import type { GeometryObjectDraft, LengthQuantityUnit, QuantityDraftField } from "@/kernel/authoring/object-edit/objectEditTypes";
import { parseDraftQuantityField } from "@/kernel/authoring/object-edit/quantityDraftFields";

import { QuantityUnitSelect } from "./QuantityUnitSelect";

export type DraftUnitUpdater = (field: QuantityDraftField, unit: LengthQuantityUnit) => void;

export function DraftQuantityUnitSelect({ draft, field, label, onChange }: {
  draft: GeometryObjectDraft;
  field: QuantityDraftField;
  label: string;
  onChange: DraftUnitUpdater;
}) {
  return <QuantityUnitSelect input={parseDraftQuantityField(draft, field)} label={label}
    onChange={(unit) => onChange(field, unit as LengthQuantityUnit)} />;
}
