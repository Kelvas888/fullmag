"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useKernel } from "@/kernel/KernelContext";
import { createCommandContext } from "@/kernel/commands/commandContext";
import {
  commitObjectMoveWorkflow,
  rebaseObjectMoveConflict,
  type ObjectMoveConflict,
} from "@/kernel/authoring/objectMoveConflictWorkflow";
import { useObjectMoveTool } from "@/kernel/authoring/ObjectMoveToolController";
import type { ObjectTranslation } from "@/kernel/authoring/objectTranslationMutation";
import { Button } from "@/shared/ui/Button";
import { useSceneResource } from "@/kernel/resources/geometryLifecycleResources";
import {
  sessionRequestScopeKey,
  sessionResourceIdentityKey,
  type SessionResourceIdentity,
} from "@/kernel/resources/sessionResourceIdentity";
import { useSessionResourceIdentity } from "@/kernel/resources/useSessionStatus";
import { useSelectionSelector } from "@/kernel/selection/useSelection";
import { selectionSnapshotEquals, type Selection } from "@/kernel/selection/selectionTypes";

import {
  isMoveCommitPending,
  tryAcquireMoveCommit,
  type MoveCommitLockToken,
  type MoveCommitHandler,
  Viewport3DMoveToolLayer,
} from "./MoveObjectGizmo";
import { buildViewport3DPrimitiveRenderModel } from "./viewport3dPrimitiveModel";

interface ActiveMoveIdentity {
  activationId: number;
  sessionIdentityKey: string | null;
  selection: Selection;
  selectionEpoch: number;
}

interface CurrentMoveContext {
  moveTargetEligible: boolean;
  selectedObjectId: string | null;
  sessionId: string | null;
  sessionIdentity: SessionResourceIdentity | null;
  sessionIdentityKey: string | null;
  sessionScopeKey: string | null;
}

interface MoveRequestFence {
  activationId: number;
  objectId: string;
  selection: Selection;
  selectionEpoch: number;
  sessionIdentity: SessionResourceIdentity;
  sessionIdentityKey: string;
  sessionScopeKey: string;
}

export interface Viewport3DMoveConflict extends ObjectMoveConflict {
  activationId: number;
  selection: Selection;
  sessionId: string | null;
  sessionIdentityKey: string | null;
  sessionScopeKey: string;
  selectionEpoch: number;
}

export function useViewport3DObjectMoveInteraction({
  moveTargetEligible,
  sceneRefetch,
  sceneRevision,
  sceneStatus,
  selectedObjectId,
  sessionId,
}: {
  moveTargetEligible: boolean;
  sceneRefetch: () => void;
  sceneRevision: number | null;
  sceneStatus: string;
  selectedObjectId: string | null;
  sessionId: string | null;
}) {
  const kernel = useKernel();
  const moveTool = useObjectMoveTool(kernel.objectMoveTool);
  const sessionIdentity = useSessionResourceIdentity();
  const currentContextRef = useRef<CurrentMoveContext | null>(null);
  const sessionIdentityKey = sessionIdentity
    ? sessionResourceIdentityKey(sessionIdentity)
    : null;
  const sessionScopeKey = sessionRequestScopeKey(sessionIdentity);
  const activationIdentityRef = useRef<ActiveMoveIdentity | null>(null);
  const selectionEpochRef = useRef(0);
  const selectionSnapshotRef = useRef(kernel.selection.get());
  const [selectionEpoch, setSelectionEpoch] = useState(0);
  const selectedSnapshot = useSelectionSelector((selection) => selection);
  const [moveConflict, setMoveConflict] =
    useState<Viewport3DMoveConflict | null>(null);
  const [moveStatus, setMoveStatus] = useState<{
    error: string | null;
    historyDegraded: boolean;
    sessionIdentityKey: string | null;
  }>({ error: null, historyDegraded: false, sessionIdentityKey: null });
  const moveError = moveStatus.sessionIdentityKey === sessionIdentityKey
    ? moveStatus.error
    : null;
  const moveHistoryDegraded = moveStatus.sessionIdentityKey === sessionIdentityKey &&
    moveStatus.historyDegraded;
  const [moveDraftResetRevision, setMoveDraftResetRevision] = useState(0);

  useEffect(() => {
    currentContextRef.current = {
      moveTargetEligible,
      selectedObjectId,
      sessionId,
      sessionIdentity,
      sessionIdentityKey,
      sessionScopeKey,
    };
  });

  const expireCanonicalActivation = useCallback(() => {
    activationIdentityRef.current = null;
    kernel.objectMoveTool.clear();
  }, [kernel.objectMoveTool]);

  useEffect(() => kernel.selection.subscribe((selection) => {
    if (selectionSnapshotEquals(selectionSnapshotRef.current, selection)) return;
    selectionSnapshotRef.current = selection;
    selectionEpochRef.current += 1;
    setSelectionEpoch(selectionEpochRef.current);
  }), [kernel.selection]);

  useEffect(() => {
    if (!moveTool) {
      activationIdentityRef.current = null;
      return;
    }
    if (
      moveTool.objectId !== selectedObjectId ||
      !moveTargetEligible ||
      (sessionIdentity !== null && sessionId !== sessionIdentity.sessionId)
    ) {
      expireCanonicalActivation();
      return;
    }
    const activeIdentity = activationIdentityRef.current;
    if (!activeIdentity || activeIdentity.activationId !== moveTool.activationId) {
      activationIdentityRef.current = {
        activationId: moveTool.activationId,
        sessionIdentityKey,
        selection: kernel.selection.get(),
        selectionEpoch: selectionEpochRef.current,
      };
      return;
    }
    const selection = kernel.selection.get();
    if (
      activeIdentity.sessionIdentityKey === null &&
      sessionIdentityKey !== null &&
      activeIdentity.selectionEpoch === selectionEpochRef.current &&
      selectionSnapshotEquals(activeIdentity.selection, selection)
    ) {
      activeIdentity.sessionIdentityKey = sessionIdentityKey;
      return;
    }
    if (
      activeIdentity.sessionIdentityKey !== sessionIdentityKey ||
      activeIdentity.selectionEpoch !== selectionEpochRef.current ||
      !selectionSnapshotEquals(activeIdentity.selection, selection)
    ) expireCanonicalActivation();
  }, [
    expireCanonicalActivation,
    kernel.selection,
    moveTargetEligible,
    moveTool,
    selectedObjectId,
    sessionId,
    sessionIdentityKey,
    sessionIdentity,
  ]);

  useEffect(
    () => () => {
      kernel.objectMoveTool.clear();
    },
    [kernel.objectMoveTool],
  );

  const isCurrentSessionScope = useCallback((fence: MoveRequestFence) => {
    const current = currentContextRef.current;
    if (
      !current ||
      current.sessionScopeKey !== fence.sessionScopeKey ||
      current.sessionIdentityKey !== fence.sessionIdentityKey
    ) return false;
    const registryScope = kernel.commands?.getSessionScopeKey?.();
    return registryScope === undefined || registryScope === fence.sessionScopeKey;
  }, [kernel.commands]);

  const isMoveRequestCurrent = useCallback((fence: MoveRequestFence) => {
    const current = currentContextRef.current;
    const active = activationIdentityRef.current;
    const selected = kernel.selection.get();
    const activeTool = kernel.objectMoveTool.getSnapshot();
    return Boolean(
      current &&
      current.moveTargetEligible &&
      current.selectedObjectId === fence.objectId &&
      current.sessionId === fence.sessionIdentity.sessionId &&
      current.sessionIdentityKey === fence.sessionIdentityKey &&
      current.sessionScopeKey === fence.sessionScopeKey &&
      isCurrentSessionScope(fence) &&
      activeTool?.activationId === fence.activationId &&
      activeTool.objectId === fence.objectId &&
      active?.activationId === fence.activationId &&
      active.sessionIdentityKey === fence.sessionIdentityKey &&
      active.selectionEpoch === fence.selectionEpoch &&
      selectionEpochRef.current === fence.selectionEpoch &&
      selectionSnapshotEquals(active.selection, selected) &&
      selectionSnapshotEquals(fence.selection, selected) &&
      selected.objectId === fence.objectId
    );
  }, [isCurrentSessionScope, kernel.objectMoveTool, kernel.selection]);

  const commitMoveRef = useRef<MoveCommitHandler | null>(null);
  const commitMove = useCallback(async (
    objectId: string,
    translation: ObjectTranslation,
    baseRevision: number,
    lock?: MoveCommitLockToken,
  ) => {
    const activeTool = kernel.objectMoveTool.getSnapshot();
    const current = currentContextRef.current;
    const activeIdentity = activationIdentityRef.current;
    const selection = kernel.selection.get();
    const activationId = activeTool?.activationId;
    if (
      activationId === undefined ||
      !current?.sessionIdentity ||
      !current.sessionIdentityKey ||
      !current.sessionScopeKey ||
      current.sessionId !== current.sessionIdentity.sessionId ||
      current.selectedObjectId !== objectId ||
      !current.moveTargetEligible ||
      activeTool.objectId !== objectId ||
      !activeIdentity ||
      activeIdentity.activationId !== activationId ||
      activeIdentity.sessionIdentityKey !== current.sessionIdentityKey ||
      activeIdentity.selectionEpoch !== selectionEpochRef.current ||
      !selectionSnapshotEquals(activeIdentity.selection, selection) ||
      selection.objectId !== objectId
    ) return false;

    const fence: MoveRequestFence = {
      activationId,
      objectId,
      selection,
      selectionEpoch: selectionEpochRef.current,
      sessionIdentity: current.sessionIdentity,
      sessionIdentityKey: current.sessionIdentityKey,
      sessionScopeKey: current.sessionScopeKey,
    };
    const handler = commitMoveRef.current;
    const releaseCommit = lock?.lockHeldByGesture
      ? null
      : handler
        ? tryAcquireMoveCommit(handler)
        : null;
    if (!lock?.lockHeldByGesture && !releaseCommit) return false;
    if (lock?.lockHeldByGesture && (!handler || !isMoveCommitPending(handler))) {
      return false;
    }

    setMoveStatus((previous) => ({
      error: null,
      historyDegraded:
        previous.sessionIdentityKey === fence.sessionIdentityKey &&
        previous.historyDegraded,
      sessionIdentityKey: fence.sessionIdentityKey,
    }));
    try {
      const historyContext = createCommandContext("ribbon", kernel, {
        isCurrentSessionScope: () => isCurrentSessionScope(fence),
        sessionScopeKey: fence.sessionScopeKey,
      });
      const committed = await commitObjectMoveWorkflow({
        api: kernel.api,
        baseRevision,
        historyContext,
        isCurrentRequest: () => isMoveRequestCurrent(fence),
        isCurrentSessionScope: () => isCurrentSessionScope(fence),
        objectId,
        onAcknowledged: () => {
          if (!isMoveRequestCurrent(fence)) return;
          setMoveConflict(null);
          setMoveStatus((previous) => ({
            error: null,
            historyDegraded:
              previous.sessionIdentityKey === fence.sessionIdentityKey &&
              previous.historyDegraded,
            sessionIdentityKey: fence.sessionIdentityKey,
          }));
          setMoveDraftResetRevision((revision) => revision + 1);
        },
        onConflict: (conflict) => {
          if (!isMoveRequestCurrent(fence)) return;
          setMoveStatus((previous) => ({
            error: null,
            historyDegraded:
              previous.sessionIdentityKey === fence.sessionIdentityKey &&
              previous.historyDegraded,
            sessionIdentityKey: fence.sessionIdentityKey,
          }));
          setMoveConflict({
            ...conflict,
            activationId,
            selection: fence.selection,
            selectionEpoch: fence.selectionEpoch,
            sessionId: fence.sessionIdentity.sessionId,
            sessionIdentityKey: fence.sessionIdentityKey,
            sessionScopeKey: fence.sessionScopeKey,
          });
        },
        onHistoryDegraded: () => {
          if (isMoveRequestCurrent(fence)) {
            setMoveStatus((previous) => ({
              error: previous.sessionIdentityKey === fence.sessionIdentityKey
                ? previous.error
                : null,
              historyDegraded: true,
              sessionIdentityKey: fence.sessionIdentityKey,
            }));
          }
        },
        resources: kernel.resources,
        sessionScopeKey: fence.sessionScopeKey,
        translation,
      });
      return committed && isMoveRequestCurrent(fence);
    } catch (error) {
      if (isMoveRequestCurrent(fence)) {
        setMoveStatus((previous) => ({
          error: error instanceof Error ? error.message : String(error),
          historyDegraded:
            previous.sessionIdentityKey === fence.sessionIdentityKey &&
            previous.historyDegraded,
          sessionIdentityKey: fence.sessionIdentityKey,
        }));
      }
      return false;
    } finally {
      releaseCommit?.();
    }
  }, [isCurrentSessionScope, isMoveRequestCurrent, kernel]);
  useEffect(() => {
    commitMoveRef.current = commitMove;
  }, [commitMove]);

  const activeMoveConflict = moveConflict &&
    moveTool?.activationId === moveConflict.activationId &&
    moveTool.objectId === moveConflict.objectId &&
    selectedObjectId === moveConflict.objectId &&
    moveTargetEligible &&
    sessionId === moveConflict.sessionId &&
    sessionIdentityKey === moveConflict.sessionIdentityKey &&
    sessionScopeKey === moveConflict.sessionScopeKey &&
    selectionEpoch === moveConflict.selectionEpoch &&
    selectionSnapshotEquals(selectedSnapshot, moveConflict.selection)
    ? moveConflict
    : null;

  const refetchMoveScene = useCallback(() => {
    if (!activeMoveConflict) return;
    sceneRefetch();
  }, [activeMoveConflict, sceneRefetch]);

  const rebaseMove = useCallback(() => {
    if (
      !activeMoveConflict ||
      sceneStatus !== "ready" ||
      sceneRevision === null ||
      sceneRevision === activeMoveConflict.baseRevision
    ) return;
    setMoveConflict({
      ...rebaseObjectMoveConflict(activeMoveConflict, sceneRevision),
      activationId: activeMoveConflict.activationId,
      selection: activeMoveConflict.selection,
      sessionId: activeMoveConflict.sessionId,
      sessionIdentityKey: activeMoveConflict.sessionIdentityKey,
      sessionScopeKey: activeMoveConflict.sessionScopeKey,
      selectionEpoch: activeMoveConflict.selectionEpoch,
    });
  }, [activeMoveConflict, sceneRevision, sceneStatus]);

  const retryMove = useCallback(async () => {
    if (
      !activeMoveConflict ||
      activeMoveConflict.phase !== "rebased"
    ) {
      return;
    }
    const retry = { ...activeMoveConflict, phase: "retrying" as const };
    setMoveConflict(retry);
    await commitMove(retry.objectId, retry.translation, retry.baseRevision);
  }, [activeMoveConflict, commitMove]);

  const canRebase = Boolean(
    activeMoveConflict?.phase === "conflict" &&
      sceneStatus === "ready" &&
      sceneRevision !== null &&
      sceneRevision !== activeMoveConflict.baseRevision,
  );

  return {
    canRebase,
    commitMove,
    moveConflict: activeMoveConflict,
    moveDraftResetRevision,
    moveError,
    moveHistoryDegraded,
    moveToolObjectId: moveTool?.objectId ?? null,
    rebaseMove,
    refetchMoveScene,
    retryMove,
    sceneStatus,
  };
}

export function Viewport3DMoveConflictPanel({
  interaction,
}: {
  interaction: ReturnType<typeof useViewport3DObjectMoveInteraction>;
}) {
  const { moveConflict, moveError, moveHistoryDegraded } = interaction;
  if (!moveConflict && !moveError && !moveHistoryDegraded) return null;
  return (
    <aside
      className="fm-viewport-3d__move-conflict"
      aria-live="polite"
      data-move-conflict={moveConflict?.phase ?? "none"}
      data-move-history={moveHistoryDegraded ? "degraded" : "ready"}
    >
      {moveConflict ? (
        <>
          <span>Scene changed. The move draft is preserved.</span>
          <Button
            disabled={
              moveConflict.phase !== "conflict" ||
              interaction.sceneStatus === "loading" ||
              interaction.sceneStatus === "stale"
            }
            size="sm"
            type="button"
            variant="ghost"
            onClick={interaction.refetchMoveScene}
          >
            Refetch Scene
          </Button>
          <Button
            disabled={!interaction.canRebase}
            size="sm"
            type="button"
            variant="ghost"
            onClick={interaction.rebaseMove}
          >
            Rebase Draft
          </Button>
          <Button
            disabled={moveConflict.phase !== "rebased"}
            size="sm"
            type="button"
            variant="primary"
            onClick={() => void interaction.retryMove()}
          >
            Retry Move
          </Button>
        </>
      ) : null}
      {moveError ? <span role="alert">Move failed: {moveError}</span> : null}
      {moveHistoryDegraded ? (
        <span role="alert">
          The move was saved, but Undo/Redo history could not capture it. History is degraded for this change.
        </span>
      ) : null}
    </aside>
  );
}

/** Production integration boundary used by qualification tests without mounting WebGL. */
export function Viewport3DObjectMoveResourceSurface() {
  const scene = useSceneResource();
  const sessionIdentity = useSessionResourceIdentity();
  const selectedObjectId = useSelectionSelector((selection) =>
    selection.ref?.type === "scene-object"
      ? selection.ref.objectId ?? selection.objectId
      : null,
  );
  const primitiveModel = useMemo(
    () => buildViewport3DPrimitiveRenderModel(scene.data, null),
    [scene.data],
  );
  const moveTargetEligible = primitiveModel.objects.some(
    (object) => object.objectId === selectedObjectId && object.role === "magnet",
  );
  const interaction = useViewport3DObjectMoveInteraction({
    moveTargetEligible,
    sceneRefetch: scene.refetch,
    sceneRevision: primitiveModel.sceneRevision,
    sceneStatus: scene.status,
    selectedObjectId,
    sessionId: sessionIdentity?.sessionId ?? null,
  });
  const [orbitBlocked, setOrbitBlocked] = useState(false);

  return (
    <div
      className="fm-viewport-3d__move-resource-surface"
      data-draft-reset-revision={interaction.moveDraftResetRevision}
      data-orbit-blocked={orbitBlocked ? "true" : "false"}
      data-scene-status={scene.status}
    >
      <Viewport3DMoveToolLayer
        moveDraftResetRevision={interaction.moveDraftResetRevision}
        moveToolObjectId={interaction.moveToolObjectId}
        onCommit={interaction.commitMove}
        onGestureActiveChange={setOrbitBlocked}
        primitiveModel={primitiveModel}
        selectedObjectId={selectedObjectId}
      />
      <Viewport3DMoveConflictPanel interaction={interaction} />
    </div>
  );
}
