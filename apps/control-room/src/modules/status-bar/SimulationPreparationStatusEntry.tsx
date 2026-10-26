"use client";

import {
  simulationPreparationWindow,
  useSimulationPreparationWindow,
} from "@/kernel/layout/simulationPreparationWindow";

/**
 * Status bar entry of the latest simulation preparation. It stays available
 * after the window is closed or the preparation finished, and reopens it.
 */
export function SimulationPreparationStatusEntry() {
  const preparation = useSimulationPreparationWindow().summary;
  if (!preparation) return null;

  return (
    <>
      <span className="fm-status-bar__sep" aria-hidden="true" />
      <span
        aria-label={`Show simulation preparation: ${preparation.title}`}
        className="fm-status-bar__item fm-status-bar__item--clickable fm-status-bar__preparation"
        data-preparation-status-entry
        data-tone={preparation.tone}
        title={preparation.title}
        role="button"
        tabIndex={0}
        onClick={simulationPreparationWindow.open}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            simulationPreparationWindow.open();
          }
        }}
      >
        Preparation: {preparation.label}
      </span>
    </>
  );
}
