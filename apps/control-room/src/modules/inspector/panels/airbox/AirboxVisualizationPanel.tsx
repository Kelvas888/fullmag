"use client";

import { useSavedFieldPresentation } from "@/kernel/visualization/useObjectVisualization";
import { SavedFieldVisualizationInspector } from "../SavedFieldVisualizationPanel";

import type { InspectorPanelProps } from "../../inspectorTypes";
import {
  VisualizationTargetInspectorPanel,
  type VisualizationInspectorOwner,
} from "../ObjectVisualizationPanel";

const AIRBOX_VISUALIZATION_OWNER: VisualizationInspectorOwner = {
  actionSummary: "Airbox extent, display passes, field quantity, and overrides",
  capabilityDescription:
    "Uses the canonical Airbox target while preserving Airbox-specific bounds and field support.",
  id: "airbox.visualization",
  targetLabel: "Airbox",
  title: "Airbox visualization",
};

export function AirboxVisualizationPanel(props: InspectorPanelProps) {
  const { presentation } = useSavedFieldPresentation();
  return presentation ? <SavedFieldVisualizationInspector /> : <CurrentAirboxVisualizationPanel {...props} />;
}

function CurrentAirboxVisualizationPanel({ selection }: InspectorPanelProps) {
  return (
    <VisualizationTargetInspectorPanel
      owner={AIRBOX_VISUALIZATION_OWNER}
      selection={selection}
    />
  );
}
