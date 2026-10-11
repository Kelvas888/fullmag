import { describe, expect, it, vi } from "vitest";

import type {
  VisualizationStatePatch,
  VisualizationStateResource,
} from "@/kernel/api/apiTypes";
import { VISUALIZATION_STATE_PATH } from "@/kernel/api/apiPaths";
import { CommandRegistry } from "@/kernel/commands/CommandRegistry";
import type { CommandContext } from "@/kernel/commands/commandTypes";
import {
  AnalysisFieldOverlayController,
  type AnalysisFieldOverlayState,
} from "@/kernel/visualization/AnalysisFieldOverlayController";

import {
  globalQuantityCommandInput,
  RIBBON_COMMANDS,
  RIBBON_VISUALIZATION_APPLY_GLOBAL_QUANTITY_COMMAND,
} from "./ribbonCommands";

function overlayForOwner(
  runId: string,
  stageId: string,
  artifactRevision: number,
): AnalysisFieldOverlayState {
  return {
    fieldId: "analysis:eigen:sample-0:mode-1",
    label: "Mode 1",
    modeIndex: 1,
    modeIntent: {
      analysisRunId: runId,
      analysisStageId: stageId,
      artifactRevision: String(artifactRevision),
      fieldId: "analysis:eigen:sample-0:mode-1",
      metadataResourceKey: `analysis/${runId}/${stageId}/mode-1/meta`,
      modeId: "sample-0/mode-1",
      modeIndex: 1,
      nodeId: `results:${runId}:${stageId}:mode-1`,
      sampleId: "sample-0",
      sampleIndex: 0,
    },
    provenance: {
      artifactRevision: String(artifactRevision),
      resourceRef: "data/fields/analysis:eigen:sample-0:mode-1",
      runId,
      stageId,
    },
    query: { view: "phase_rotated_real" },
    sampleIndex: 0,
    source: "eigen-mode",
  };
}

function visualizationState(revision: number): VisualizationStateResource {
  return {
    active_quantity_id: "H_eff",
    overrides: [],
    quantity: { active_quantity_id: "H_eff" },
    revision,
  } as VisualizationStateResource;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function executeGlobalQuantityCommand(
  overlay: AnalysisFieldOverlayController,
  patch: (value: VisualizationStatePatch) => Promise<VisualizationStateResource>,
) {
  const command = RIBBON_COMMANDS.find(
    ({ id }) => id === RIBBON_VISUALIZATION_APPLY_GLOBAL_QUANTITY_COMMAND,
  );
  if (!command) throw new Error("Global quantity command is not registered.");

  const registry = new CommandRegistry();
  registry.register(command);
  const context: CommandContext = {
    analysisFieldOverlay: overlay,
    api: { visualization: { patch } } as unknown as NonNullable<CommandContext["api"]>,
    resourceData: {
      [VISUALIZATION_STATE_PATH]: visualizationState(7),
    },
    source: "test",
  };
  return registry.execute(
    RIBBON_VISUALIZATION_APPLY_GLOBAL_QUANTITY_COMMAND,
    context,
    globalQuantityCommandInput("H_eff", true),
  );
}

describe("Ribbon global quantity overlay cleanup", () => {
  it("clears the original overlay after the quantity patch is acknowledged", async () => {
    const overlay = new AnalysisFieldOverlayController();
    overlay.set(overlayForOwner("run-1", "stage-1", 4));
    const patch = vi.fn(async () => visualizationState(8));

    const result = await executeGlobalQuantityCommand(overlay, patch);

    expect(result.status).toBe("completed");
    expect(overlay.getSnapshot()).toBeNull();
  });

  it("preserves a newer typed overlay when an older patch ACK arrives", async () => {
    const overlay = new AnalysisFieldOverlayController();
    overlay.set(overlayForOwner("run-old", "stage-old", 4));
    const acknowledgement = deferred<VisualizationStateResource>();
    const patch = vi.fn(() => acknowledgement.promise);

    const pendingCommand = executeGlobalQuantityCommand(overlay, patch);
    expect(patch).toHaveBeenCalledOnce();

    overlay.set(overlayForOwner("run-new", "stage-new", 5));
    const newerOverlay = overlay.getSnapshot();
    acknowledgement.resolve(visualizationState(8));

    const result = await pendingCommand;

    expect(result.status).toBe("completed");
    expect(overlay.getSnapshot()).toBe(newerOverlay);
    expect(overlay.getSnapshot()).toMatchObject({
      fieldId: "analysis:eigen:sample-0:mode-1",
      modeIntent: {
        analysisRunId: "run-new",
        analysisStageId: "stage-new",
        artifactRevision: "5",
      },
      provenance: {
        artifactRevision: "5",
        runId: "run-new",
        stageId: "stage-new",
      },
    });
  });

  it("preserves an overlay created during the patch when none existed initially", async () => {
    const overlay = new AnalysisFieldOverlayController();
    const acknowledgement = deferred<VisualizationStateResource>();
    const patch = vi.fn(() => acknowledgement.promise);

    const pendingCommand = executeGlobalQuantityCommand(overlay, patch);
    expect(patch).toHaveBeenCalledOnce();

    overlay.set(overlayForOwner("run-new", "stage-new", 5));
    const newerOverlay = overlay.getSnapshot();
    acknowledgement.resolve(visualizationState(8));

    const result = await pendingCommand;

    expect(result.status).toBe("completed");
    expect(overlay.getSnapshot()).toBe(newerOverlay);
  });

  it("preserves the original overlay when the quantity patch is rejected", async () => {
    const overlay = new AnalysisFieldOverlayController();
    overlay.set(overlayForOwner("run-1", "stage-1", 4));
    const originalOverlay = overlay.getSnapshot();
    const patch = vi.fn(async () => {
      throw new Error("visualization update rejected");
    });

    const result = await executeGlobalQuantityCommand(overlay, patch);

    expect(result.status).toBe("failed");
    expect(overlay.getSnapshot()).toBe(originalOverlay);
  });
});
