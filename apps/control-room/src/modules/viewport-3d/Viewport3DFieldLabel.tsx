import type { ArtifactFieldOverlayModel } from "./model/artifactFieldOverlayModel";

/** Historical inspection owns the field identity while its live layers are suppressed. */
export function Viewport3DFieldLabel({ quantityId, label, historical, model, error }: {
  quantityId: string;
  label: string;
  historical: boolean;
  model: ArtifactFieldOverlayModel | null;
  error: string | null;
}) {
  const field = historical ? model : null;
  const state = historical ? field ? "ready" : error ? "unavailable" : "loading" : undefined;
  return <span data-quantity-id={field?.quantityId ?? quantityId} data-field-state={state} title={historical && error ? error : undefined}>
    {field ? `${field.quantityId} [${field.unit}]` : historical ? `${label} · ${error ? "unavailable" : "loading"}` : label}
  </span>;
}
