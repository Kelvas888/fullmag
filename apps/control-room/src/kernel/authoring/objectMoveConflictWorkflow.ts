import type { ControlRoomApi } from "@/kernel/api/ControlRoomApi";
import type { CommandContext } from "@/kernel/commands/commandTypes";
import type { ResourceInvalidationController } from "@/kernel/resources/ResourceInvalidationController";

import {
  commitObjectTranslation,
  isObjectTranslationRevisionConflict,
  type ObjectTranslation,
} from "./objectTranslationMutation";
import {
  prepareAuthoringMutation,
  recordAuthoringMutationHistory,
} from "./authoringHistoryMutation";

type ObjectMoveHistoryContext = Pick<
  CommandContext,
  | "api"
  | "authoringHistory"
  | "isCurrentSessionScope"
  | "resourceData"
  | "selection"
  | "sessionScopeKey"
>;

export interface ObjectMoveConflict {
  baseRevision: number;
  objectId: string;
  phase: "conflict" | "rebased" | "retrying";
  translation: ObjectTranslation;
}

export async function commitObjectMoveWorkflow(options: {
  api: ControlRoomApi;
  baseRevision: number;
  objectId: string;
  onAcknowledged: () => void;
  onConflict: (conflict: ObjectMoveConflict) => void;
  onHistoryDegraded?: () => void;
  historyContext?: ObjectMoveHistoryContext;
  isCurrentRequest?: () => boolean;
  resources: ResourceInvalidationController;
  sessionScopeKey?: string;
  isCurrentSessionScope?: () => boolean;
  translation: ObjectTranslation;
}): Promise<boolean> {
  let historyPreparation: Awaited<ReturnType<typeof prepareAuthoringMutation>> | null = null;
  let historyCaptureFailed = false;
  if (options.historyContext?.authoringHistory) {
    try {
      historyPreparation = await prepareAuthoringMutation(options.historyContext);
      historyCaptureFailed =
        !historyPreparation.before ||
        historyPreparation.baseRevision !== options.baseRevision;
    } catch {
      historyCaptureFailed = true;
    }
  }
  if (options.isCurrentRequest?.() === false || options.isCurrentSessionScope?.() === false) {
    return false;
  }

  try {
    const result = await commitObjectTranslation({
      ...options,
      isCurrentSessionScope: options.isCurrentSessionScope,
      sessionScopeKey: options.sessionScopeKey,
    });
    const history = options.historyContext?.authoringHistory;
    const historyContext = options.historyContext;
    if (history && historyContext?.isCurrentSessionScope?.() !== false) {
      if (historyCaptureFailed || !historyPreparation) {
        options.onHistoryDegraded?.();
      } else {
        const label = `Move ${options.objectId} at scene revision ${options.baseRevision} to ${result.revision}`;
        try {
          await recordAuthoringMutationHistory(
            historyContext,
            label,
            historyPreparation,
            result.committedScene,
          );
          if (
            result.revision > options.baseRevision &&
            history.getSnapshot().undoLabel !== label
          ) {
            options.onHistoryDegraded?.();
          }
        } catch {
          options.onHistoryDegraded?.();
        }
      }
    }
    options.onAcknowledged();
    return true;
  } catch (error) {
    if (!isObjectTranslationRevisionConflict(error)) throw error;
    options.onConflict({
      baseRevision: options.baseRevision,
      objectId: options.objectId,
      phase: "conflict",
      translation: [...options.translation],
    });
    return false;
  }
}

export function rebaseObjectMoveConflict(
  conflict: ObjectMoveConflict,
  sceneRevision: number,
): ObjectMoveConflict {
  return { ...conflict, baseRevision: sceneRevision, phase: "rebased" };
}
