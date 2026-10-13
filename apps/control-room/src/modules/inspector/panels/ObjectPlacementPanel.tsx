import type { GeometryObjectDraft } from "@/kernel/authoring/object-edit/objectEditTypes";
import { PROBLEM_IR_03_RIGID_TRANSFORM_REASON } from "@/kernel/authoring/objectTranslationMutation";

import { FieldRow } from "../primitives/FieldRow";
import { InspectorGroup } from "../primitives/InspectorGroup";
import { Vector3Field } from "../primitives/Vector3Field";

type PlacementVectorField = "rotation" | "scale" | "translation";

export function ObjectPlacementPanel({
  draft,
  errors,
  onVectorChange,
}: {
  draft: GeometryObjectDraft;
  errors: Readonly<Record<string, string>>;
  onVectorChange: (
    field: PlacementVectorField,
    index: 0 | 1 | 2,
    value: string,
  ) => void;
}) {
  return (
    <InspectorGroup title="Placement" collapsible defaultOpen>
      <Vector3Field
        errors={[
          errors["translation.0"],
          errors["translation.1"],
          errors["translation.2"],
        ]}
        label="Translation"
        unit="m"
        values={draft.translation}
        onChange={(index, value) => onVectorChange("translation", index, value)}
      />
      <Vector3Field
        disabled
        label="Rotation"
        unit="rad"
        values={draft.rotation}
        onChange={(index, value) => onVectorChange("rotation", index, value)}
      />
      <Vector3Field
        disabled
        label="Scale"
        unit="x"
        values={draft.scale}
        onChange={(index, value) => onVectorChange("scale", index, value)}
      />
      <FieldRow label="Rotate / Scale" value={PROBLEM_IR_03_RIGID_TRANSFORM_REASON} />
    </InspectorGroup>
  );
}
