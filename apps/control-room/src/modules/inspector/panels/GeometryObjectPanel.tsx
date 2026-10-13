import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { JsonObject, SceneResource } from "@/kernel/api/apiTypes";
import { MODEL_SCENE_PATH } from "@/kernel/api/apiPaths";
import { runAuthoringMutationWithHistory } from "@/kernel/authoring/authoringHistoryMutation";
import {
  acknowledgedAuthoringSceneRevision,
  invalidateAuthoringMutationDependents,
} from "@/kernel/authoring/authoringMutationInvalidation";
import {
  createObjectTransaction,
  patchObjectGeometryTransaction,
  primitiveDraftOverlayStore,
} from "@/kernel/authoring/geometryLifecycleCommands";
import { useKernel } from "@/kernel/KernelContext";
import { useObjectEditSelector } from "@/kernel/authoring/object-edit/useObjectEditSelector";
import { geometryObjectEditSessionTargetKey } from "@/kernel/authoring/object-edit/objectEditDraftModel";
import {
  publishCommittedSceneResource,
  useGeometryValidationResource,
  useSceneResource,
} from "@/kernel/resources/geometryLifecycleResources";
import { Button } from "@/shared/ui/Button";

import type { InspectorPanelProps } from "../inspectorTypes";
import { useRegisterInspectorEditSession } from "../InspectorEditSession";
import { FeedbackBanner } from "../primitives/FeedbackBanner";
import { FieldRow } from "../primitives/FieldRow";
import { FormField } from "../primitives/FormField";
import { InspectorGroup } from "../primitives/InspectorGroup";
import { useInspectorActiveTab } from "../InspectorTabState";
import { ObjectPlacementPanel } from "./ObjectPlacementPanel";
import { Vector3Field } from "../primitives/Vector3Field";
import {
  buildGeometryDraftPatch,
  buildTransformDraftPatch,
  geometryDraftGeometryEquals,
  geometryDraftTranslationEquals,
  createDraftObjectId,
  resolveGeometryObjectDraft,
  resolveGeometryObjectPanelModel,
  resolvePrimitiveDraft,
  isPrimitiveDraftRevisionConflict,
  rebaseGeometryObjectDraft,
  summarizeGeometryValidationMessages,
  type GeometryObjectDraft,
} from "./geometryObjectPanelModel";

type Feedback = {
  kind: "error" | "success";
  message: string;
};

interface FeedbackState {
  feedback: Feedback | null;
  key: string;
}

interface PendingOperationState {
  draftKey: string;
  operationId: number;
  pending: boolean;
  sessionScopeKey: string | null;
}

type VectorDraftField = "rotation" | "scale" | "size" | "translation";
type DraftField =
  | "archHeight"
  | "height"
  | "length"
  | "material"
  | "name"
  | "notes"
  | "radius"
  | "region"
  | "width"
  | "z0";
type DraftFieldUpdater = (field: DraftField, value: string) => void;
type VectorDraftUpdater = (
  field: VectorDraftField,
  index: 0 | 1 | 2,
  value: string,
) => void;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function optionalRef(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed && trimmed !== "unassigned" ? trimmed : undefined;
}

function sameDraftFields(
  left: GeometryObjectDraft,
  right: GeometryObjectDraft,
  fields: readonly (keyof GeometryObjectDraft)[],
): boolean {
  return fields.every((field) => JSON.stringify(left[field]) === JSON.stringify(right[field]));
}

function sameDraftValues(left: GeometryObjectDraft, right: GeometryObjectDraft): boolean {
  return sameDraftFields(left, right, [
    "archHeight",
    "geometryKind",
    "height",
    "length",
    "material",
    "name",
    "radius",
    "region",
    "size",
    "translation",
    "width",
    "z0",
  ]);
}

function mergeGeometryDescriptor(existing: JsonObject, edited: JsonObject): JsonObject {
  const existingParams = existing.geometry_params;
  const editedParams = edited.geometry_params;
  const mergedParams =
    existingParams && typeof existingParams === "object" && !Array.isArray(existingParams) &&
    editedParams && typeof editedParams === "object" && !Array.isArray(editedParams)
      ? { ...existingParams, ...editedParams }
      : editedParams;
  return {
    ...existing,
    ...edited,
    ...(mergedParams ? { geometry_params: mergedParams } : {}),
  };
}

function invalidateAuthoringResources(
  resources: ReturnType<typeof useKernel>["resources"],
  revision: number,
  committedScene?: SceneResource,
  sessionScopeKey?: string | null,
  resourceCacheScope?: string | null,
): void {
  if (committedScene) {
    publishCommittedSceneResource(
      resources,
      committedScene,
      revision,
      undefined,
      false,
      sessionScopeKey,
      resourceCacheScope,
    );
  }
  invalidateAuthoringMutationDependents(resources, "geometry", revision);
}

export function GeometryObjectPanel({ selection }: InspectorPanelProps) {
  const {
    api,
    authoringHistory,
    commands,
    layout,
    objectEditSession,
    resources,
    selection: selectionController,
  } = useKernel();
  const scene = useSceneResource();
  const validation = useGeometryValidationResource();
  const object = resolveGeometryObjectPanelModel(selection, scene.data);

  const baseDraft = useMemo(
    () => resolveGeometryObjectDraft(selection, scene.data),
    [scene.data, selection],
  );
  const currentSessionScopeKey = commands.getSessionScopeKey() ?? null;
  const draftKey = baseDraft.mode + ":" + baseDraft.objectId;
  const targetKey = geometryObjectEditSessionTargetKey(currentSessionScopeKey, baseDraft);
  const editSnapshot = useObjectEditSelector(objectEditSession);
  const sessionMatchesTarget = editSnapshot.identity?.targetKey === targetKey;
  const editIdentity = sessionMatchesTarget ? editSnapshot.identity : null;
  const draft = sessionMatchesTarget
    ? editSnapshot.draft ?? baseDraft
    : baseDraft;
  const [feedbackState, setFeedbackState] = useState<FeedbackState>({
    feedback: null,
    key: draftKey,
  });
  const [pendingState, setPendingState] = useState<PendingOperationState>({
    draftKey,
    operationId: 0,
    pending: false,
    sessionScopeKey: currentSessionScopeKey,
  });
  const pendingOperationId = useRef(0);
  const preConflictBaselineRef = useRef<GeometryObjectDraft | null>(null);
  const pending =
    (pendingState.pending &&
      pendingState.draftKey === draftKey &&
      pendingState.sessionScopeKey === currentSessionScopeKey) ||
    (sessionMatchesTarget && editSnapshot.applyOperationId !== null);
  const [revisionConflictPhase, setRevisionConflictPhase] = useState<
    "conflict" | "refresh-error" | "refreshing" | "rebased" | "refetched" | null
  >(null);
  const [conflictBaseRevision, setConflictBaseRevision] = useState<number | null>(null);
  const [conflictOperation, setConflictOperation] = useState<
    "create" | "geometry" | "transform"
  >("create");
  const [refreshSawLoading, setRefreshSawLoading] = useState(false);
  const feedback =
    feedbackState.key === draftKey ? feedbackState.feedback : null;
  const validationMessages = summarizeGeometryValidationMessages(
    validation.data,
    draft.objectId,
  );
  const primitiveDraft = useMemo(() => resolvePrimitiveDraft(draft), [draft]);
  const activeTab = useInspectorActiveTab();

  useLayoutEffect(() => {
    const identity = objectEditSession.activate({
      objectId: baseDraft.objectId,
      sessionScopeKey: currentSessionScopeKey,
      targetKey,
    }, baseDraft);
    objectEditSession.refreshCanonical(identity, baseDraft);
  }, [baseDraft, currentSessionScopeKey, objectEditSession, targetKey]);

  function createHistoryMutationContext() {
    const sessionScopeKey = commands.getSessionScopeKey();
    const historyGeneration = authoringHistory?.getGeneration?.();
    return {
      api,
      authoringHistory,
      layout,
      resourceData: { [MODEL_SCENE_PATH]: scene.data },
      selection: selectionController,
      sessionScopeKey: sessionScopeKey ?? null,
      isCurrentSessionScope: () =>
        commands.getSessionScopeKey() === sessionScopeKey &&
        (historyGeneration === undefined ||
          authoringHistory?.getGeneration?.() === historyGeneration),
    };
  }

  useEffect(() => {
    if (draft.mode === "draft-new") {
      primitiveDraftOverlayStore.publish(primitiveDraft);
    } else {
      primitiveDraftOverlayStore.clear();
    }
  }, [draft.mode, primitiveDraft]);
  useEffect(() => () => primitiveDraftOverlayStore.clear(), []);
  useEffect(() => {
    if (revisionConflictPhase !== "refreshing") return;
    let cancelled = false;
    const updateAfterResourceTransition = (update: () => void) => {
      queueMicrotask(() => {
        if (!cancelled) update();
      });
    };
    if (scene.status === "loading") {
      updateAfterResourceTransition(() => setRefreshSawLoading(true));
    } else if (scene.status === "error") {
      updateAfterResourceTransition(() => {
        setRevisionConflictPhase("refresh-error");
        setFeedbackState({
          feedback: {
            kind: "error",
            message:
              scene.error?.message ??
              "Scene refetch failed. Retry refetch before rebasing.",
          },
          key: draftKey,
        });
      });
    } else if (
      refreshSawLoading &&
      scene.status === "ready" &&
      baseDraft.baseRevision !== null &&
      baseDraft.baseRevision !== conflictBaseRevision
    ) {
      updateAfterResourceTransition(() => {
        setRevisionConflictPhase("refetched");
        setFeedbackState({
          feedback: {
            kind: "error",
            message: "Scene refetched. Rebase the preserved draft before retrying.",
          },
          key: draftKey,
        });
      });
    }
    return () => {
      cancelled = true;
    };
  }, [
    baseDraft.baseRevision,
    conflictBaseRevision,
    draftKey,
    refreshSawLoading,
    revisionConflictPhase,
    scene.error,
    scene.status,
  ]);

  function updateDraft(updater: (current: GeometryObjectDraft) => GeometryObjectDraft): void {
    if (!editIdentity) return;
    objectEditSession.updateDraft(editIdentity, updater);
  }

  function setFeedback(feedbackValue: Feedback | null): void {
    setFeedbackState({
      feedback: feedbackValue,
      key: draftKey,
    });
  }

  function beginPendingOperation(): () => void {
    const operationId = ++pendingOperationId.current;
    const sessionScopeKey = commands.getSessionScopeKey() ?? null;
    setPendingState({ draftKey, operationId, pending: true, sessionScopeKey });
    return () => {
      setPendingState((current) =>
        current.operationId === operationId
          ? { ...current, pending: false }
          : current,
      );
    };
  }

  function updateField(field: DraftField, value: string): void {
    updateDraft((current) => ({ ...current, [field]: value }));
  }

  function updateVector(
    field: VectorDraftField,
    index: 0 | 1 | 2,
    value: string,
  ): void {
    updateDraft((current) => {
      const next = [...current[field]] as [string, string, string];
      next[index] = value;
      return { ...current, [field]: next };
    });
  }

  const geometryDraftChanged =
    draft.mode === "committed" && !geometryDraftGeometryEquals(draft, baseDraft);
  const transformDraftChanged =
    draft.mode === "committed" && !geometryDraftTranslationEquals(draft, baseDraft);
  const newObjectDraftChanged = draft.mode === "draft-new" && !sameDraftValues(draft, baseDraft);
  const inspectorDirty = geometryDraftChanged || transformDraftChanged || newObjectDraftChanged;
  const geometryPatch = buildGeometryDraftPatch(draft);
  const existingObject = scene.data?.objects?.find((candidate) => candidate.id === draft.objectId);
  const transformPatch = buildTransformDraftPatch(
    draft,
    draft.mode === "committed" ? existingObject?.transform : undefined,
  );

  useEffect(() => {
    if (editIdentity) objectEditSession.setDirty(editIdentity, inspectorDirty);
  }, [editIdentity, inspectorDirty, objectEditSession]);
  const inspectorValid = !inspectorDirty || (
    draft.baseRevision !== null &&
    Object.keys(primitiveDraft.errors).length === 0 &&
    (draft.mode !== "draft-new" || (geometryPatch.error === null && transformPatch.error === null)) &&
    (!geometryDraftChanged || geometryPatch.error === null) &&
    (!inspectorDirty || transformPatch.error === null)
  );
  const inspectorApplyBlockReason =
    revisionConflictPhase !== null && revisionConflictPhase !== "rebased"
      ? "Resolve the scene revision conflict before applying this draft."
      : undefined;

  async function applyRegisteredDraft(): Promise<boolean> {
    if (draft.mode === "draft-new") return applyCreateDraft();
    if (draft.mode === "committed") return applyObjectDraft();
    return false;
  }

  const acknowledgeCommittedDraft = useRegisterInspectorEditSession(
    draft.mode === "missing" ? null : "staged",
    pending,
    inspectorDirty,
    inspectorValid,
    undefined,
    applyRegisteredDraft,
    revertDraft,
    {
      applyBlockReason: inspectorApplyBlockReason,
      historyMode: "mutation-owned",
    },
  );


  async function applyCreateDraft(): Promise<boolean> {
    if (draft.baseRevision === null) {
      setFeedback({ kind: "error", message: "The canonical scene revision is unavailable. Refetch the scene before applying." });
      return false;
    }
    const baseRevision = draft.baseRevision;
    const geometry = buildGeometryDraftPatch(draft);
    const geometryPayload = geometry.geometry;
    if (geometry.error || !geometryPayload) {
      setFeedback({ kind: "error", message: geometry.error ?? "Invalid geometry draft." });
      return false;
    }
    const transform = buildTransformDraftPatch(draft);
    const transformPayload = transform.transform;
    if (transform.error || !transformPayload) {
      setFeedback({ kind: "error", message: transform.error ?? "Invalid transform draft." });
      return false;
    }

    const finishPending = beginPendingOperation();
    setRevisionConflictPhase(null);
    let isCurrentMutationContext: (() => boolean) | null = null;
    let selectedCreatedObject = false;
    try {
      const objectId = createDraftObjectId(draft);
      const historyContext = createHistoryMutationContext();
      isCurrentMutationContext = historyContext.isCurrentSessionScope;
      const requestOptions = historyContext.sessionScopeKey
        ? { sessionScopeKey: historyContext.sessionScopeKey }
        : undefined;
      const response = await runAuthoringMutationWithHistory(
        historyContext,
        `Create ${draft.name.trim() || objectId}`,
        async () => {
          const created = await createObjectTransaction(api, {
            base_revision: baseRevision,
            geometry: geometryPayload,
            material_ref: optionalRef(draft.material),
            name: draft.name.trim() || objectId,
            object_id: objectId,
            region_name: optionalRef(draft.region),
            transform: transformPayload,
          }, requestOptions);
          if (historyContext.isCurrentSessionScope() !== false && acknowledgeCommittedDraft()) {
            objectEditSession.clear();
            preConflictBaselineRef.current = null;
            selectionController.set(
              {
                kind: "object.root",
                label: draft.name.trim() || objectId,
                nodeId: `model:object:${objectId}`,
                objectId,
                ref: {
                  kind: "object.root",
                  nodeId: `model:object:${objectId}`,
                  objectId,
                  type: "scene-object",
                  visualizationTargetId: `object:${objectId}`,
                },
              },
              "geometry-authoring",
            );
            selectedCreatedObject = true;
          }
          return created;
        },
        undefined,
        { captureWorkspaceStateAfter: () => selectedCreatedObject },
      );
      if (historyContext.isCurrentSessionScope() === false) return false;
      const revision = acknowledgedAuthoringSceneRevision(response);
      invalidateAuthoringResources(
        resources,
        revision,
        response.committed_scene,
        historyContext.sessionScopeKey,
        api.resourceCacheScope,
      );
      preConflictBaselineRef.current = null;
      setFeedback({ kind: "success", message: "Object draft committed." });
      return true;
    } catch (error) {
      if (isCurrentMutationContext?.() === false) return false;
      if (isPrimitiveDraftRevisionConflict(error)) {
        preConflictBaselineRef.current = baseDraft;
        setConflictOperation("create");
        setRevisionConflictPhase("conflict");
        setConflictBaseRevision(draft.baseRevision);
        setRefreshSawLoading(false);
      }
      setFeedback({ kind: "error", message: errorMessage(error) });
      return false;
    } finally {
      finishPending();
    }
  }

  function refetchAfterConflict(): void {
    setRefreshSawLoading(false);
    setRevisionConflictPhase("refreshing");
    setFeedback({ kind: "error", message: "Refetching the canonical scene…" });
    scene.refetch();
  }

  function rebaseAfterConflict(): void {
    const baseline = preConflictBaselineRef.current;
    updateDraft((current) =>
      rebaseGeometryObjectDraft(current, baseDraft, baseline),
    );
    setRevisionConflictPhase("rebased");
    setFeedback({ kind: "error", message: "Draft rebased to the latest scene revision. Review and retry Apply." });
  }

  async function applyObjectDraft(): Promise<boolean> {
    if (draft.mode !== "committed" || !inspectorDirty) return false;
    if (draft.baseRevision === null) {
      setFeedback({ kind: "error", message: "The canonical scene revision is unavailable. Refetch the scene before applying." });
      return false;
    }
    if (!existingObject || !existingObject.geometry || !editIdentity) {
      setFeedback({ kind: "error", message: "The canonical object geometry or edit identity is unavailable. Refetch the scene before applying." });
      return false;
    }

    const editedGeometry = buildGeometryDraftPatch(draft);
    if (geometryDraftChanged && (editedGeometry.error || !editedGeometry.geometry)) {
      setFeedback({ kind: "error", message: editedGeometry.error ?? "Invalid geometry draft." });
      return false;
    }
    const transform = buildTransformDraftPatch(draft, existingObject.transform);
    if (transform.error || !transform.transform) {
      setFeedback({ kind: "error", message: transform.error ?? "Invalid transform draft." });
      return false;
    }
    const geometryPayload = geometryDraftChanged
      ? mergeGeometryDescriptor(existingObject.geometry as unknown as JsonObject, editedGeometry.geometry as JsonObject)
      : (existingObject.geometry as unknown as JsonObject);
    const operation = objectEditSession.beginApply(editIdentity);
    if (!operation) return false;
    const finishPending = beginPendingOperation();
    let isCurrentMutationContext: (() => boolean) | null = null;
    try {
      const historyContext = createHistoryMutationContext();
      isCurrentMutationContext = historyContext.isCurrentSessionScope;
      const requestOptions = historyContext.sessionScopeKey
        ? { sessionScopeKey: historyContext.sessionScopeKey }
        : undefined;
      let historyDegraded = false;
      const response = await runAuthoringMutationWithHistory(
        historyContext,
        "Edit geometry and placement " + draft.name,
        () => patchObjectGeometryTransaction(api, draft.objectId, {
          base_revision: draft.baseRevision as number,
          geometry: geometryPayload,
          transform: transform.transform as JsonObject,
        }, requestOptions),
        undefined,
        {
          onHistoryDegraded: () => {
            historyDegraded = true;
          },
        },
      );
      if (historyContext.isCurrentSessionScope() === false) {
        objectEditSession.reject(operation);
        return false;
      }
      const canonicalDraft = resolveGeometryObjectDraft(selection, response.committed_scene);
      const currentEpoch = objectEditSession.acknowledge(
        operation,
        canonicalDraft,
        (currentDraft, submittedDraft, acknowledgedDraft) => {
          const mergedDraft = { ...acknowledgedDraft };
          for (const field of Object.keys(currentDraft) as (keyof GeometryObjectDraft)[]) {
            if (
              JSON.stringify(currentDraft[field]) !==
              JSON.stringify(submittedDraft[field])
            ) {
              Object.assign(mergedDraft, { [field]: currentDraft[field] });
            }
          }
          const dirty =
            !geometryDraftGeometryEquals(mergedDraft, acknowledgedDraft) ||
            !geometryDraftTranslationEquals(mergedDraft, acknowledgedDraft);
          return { dirty, draft: mergedDraft };
        },
      );
      invalidateAuthoringResources(
        resources,
        response.scene_revision,
        response.committed_scene,
        historyContext.sessionScopeKey,
        api.resourceCacheScope,
      );
      if (!currentEpoch) return false;
      preConflictBaselineRef.current = null;
      setRevisionConflictPhase(null);
      setFeedback({
        kind: historyDegraded ? "warning" : "success",
        message: historyDegraded
          ? "Geometry and placement committed, but undo history was not recorded."
          : "Geometry and placement committed.",
      });
      return true;
    } catch (error) {
      const operationIsCurrent = objectEditSession.reject(operation);
      if (!operationIsCurrent || isCurrentMutationContext?.() === false) return false;
      if (isPrimitiveDraftRevisionConflict(error)) {
        preConflictBaselineRef.current = baseDraft;
        setConflictOperation("geometry");
        setRevisionConflictPhase("conflict");
        setConflictBaseRevision(draft.baseRevision);
        setRefreshSawLoading(false);
      }
      setFeedback({ kind: "error", message: errorMessage(error) });
      return false;
    } finally {
      finishPending();
    }
  }

  function revertDraft(): void {
    if (editIdentity) objectEditSession.reset(editIdentity, baseDraft);
    setRevisionConflictPhase(null);
    preConflictBaselineRef.current = null;
    setFeedback(null);
  }


  return (
    <div className="fm-inspector-panel grid min-w-0 gap-fm-inspector-group">
      <InspectorGroup title="Geometry Object" collapsible defaultOpen>
        {draft.mode === "committed" && (
          <FieldRow label="Object ID" value={object.objectId} />
        )}
        <FieldRow label="Shape" value={object.shape} />
        <FieldRow label="Dimensions" value={object.dimensions} />
      </InspectorGroup>

      {activeTab === "placement" ? (
        <ObjectPlacementPanel
          draft={draft}
          errors={primitiveDraft.errors}
          onVectorChange={updateVector}
        />
      ) : activeTab === "geometry" ? (
        <PrimitiveGeometrySection
          draft={draft}
          errors={primitiveDraft.errors}
          onFieldChange={updateField}
          onVectorChange={updateVector}
        />
      ) : (
        <>
          <PrimitiveGeometrySection
            draft={draft}
            errors={primitiveDraft.errors}
            onFieldChange={updateField}
            onVectorChange={updateVector}
          />
          <ObjectPlacementPanel
            draft={draft}
            errors={primitiveDraft.errors}
            onVectorChange={updateVector}
          />
        </>
      )}
      <DraftIdentitySection draft={draft} onFieldChange={updateField} />
      <ActionsSection
        draft={draft}
        feedback={feedback}
        pending={pending}
        onApplyCreateDraft={applyCreateDraft}
        onRebaseAfterConflict={rebaseAfterConflict}
        onRefetchAfterConflict={refetchAfterConflict}
        onRetryAfterConflict={
          conflictOperation === "create" ? applyCreateDraft : applyObjectDraft
        }
        revisionConflictPhase={revisionConflictPhase}
      />
      <ValidationSection
        messages={validationMessages}
        status={validation.status}
      />
    </div>
  );
}

function PrimitiveGeometrySection({
  draft,
  errors,
  onFieldChange,
  onVectorChange,
}: {
  draft: GeometryObjectDraft;
  errors: Readonly<Record<string, string>>;
  onFieldChange: DraftFieldUpdater;
  onVectorChange: VectorDraftUpdater;
}) {
  return (
    <InspectorGroup title="Primitive Geometry" collapsible defaultOpen>
      <FieldRow label="Kind" value={draft.geometryKind} />
      <PrimitiveGeometryFields
        draft={draft}
        errors={errors}
        onFieldChange={onFieldChange}
        onVectorChange={onVectorChange}
      />
    </InspectorGroup>
  );
}

function PrimitiveGeometryFields({
  draft,
  errors,
  onFieldChange,
  onVectorChange,
}: {
  draft: GeometryObjectDraft;
  errors: Readonly<Record<string, string>>;
  onFieldChange: DraftFieldUpdater;
  onVectorChange: VectorDraftUpdater;
}) {
  const geometryKind = draft.geometryKind.toLowerCase();
  if (geometryKind === "cylinder") {
    return (
      <>
        <FormField
          error={errors.radius}
          label="Radius"
          type="number"
          unit="m"
          value={draft.radius}
          onChange={(event) => onFieldChange("radius", event.target.value)}
        />
        <FormField
          error={errors.height}
          label="Height"
          type="number"
          unit="m"
          value={draft.height}
          onChange={(event) => onFieldChange("height", event.target.value)}
        />
      </>
    );
  }

  if (geometryKind === "sphere") {
    return (
      <FormField
        error={errors.radius}
        label="Radius"
        type="number"
        unit="m"
        value={draft.radius}
        onChange={(event) => onFieldChange("radius", event.target.value)}
      />
    );
  }

  if (geometryKind === "archwaveguide" || geometryKind === "arch_waveguide") {
    return (
      <>
        <FormField
          label="Length"
          type="number"
          unit="m"
          value={draft.length}
          onChange={(event) => onFieldChange("length", event.target.value)}
        />
        <FormField
          label="Width"
          type="number"
          unit="m"
          value={draft.width}
          onChange={(event) => onFieldChange("width", event.target.value)}
        />
        <FormField
          label="Height"
          type="number"
          unit="m"
          value={draft.height}
          onChange={(event) => onFieldChange("height", event.target.value)}
        />
        <FormField
          label="Arch height"
          type="number"
          unit="m"
          value={draft.archHeight}
          onChange={(event) => onFieldChange("archHeight", event.target.value)}
        />
        <FormField
          label="z0"
          type="number"
          unit="m"
          value={draft.z0}
          onChange={(event) => onFieldChange("z0", event.target.value)}
        />
      </>
    );
  }

  return (
    <DraftVectorFormField
      errors={[errors["size.0"], errors["size.1"], errors["size.2"]]}
      label="Size"
      unit="m"
      values={draft.size}
      onChange={(index, value) => onVectorChange("size", index, value)}
    />
  );
}

function DraftIdentitySection({
  draft,
  onFieldChange,
}: {
  draft: GeometryObjectDraft;
  onFieldChange: DraftFieldUpdater;
}) {
  if (draft.mode !== "draft-new") return null;

  return (
    <InspectorGroup title="Draft Identity" collapsible defaultOpen>
      <FormField
        label="Name"
        mono={false}
        type="text"
        value={draft.name}
        onChange={(event) => onFieldChange("name", event.target.value)}
      />
      <FormField
        label="Region"
        mono={false}
        type="text"
        value={draft.region}
        onChange={(event) => onFieldChange("region", event.target.value)}
      />
      <FormField
        label="Material"
        mono={false}
        type="text"
        value={draft.material}
        onChange={(event) => onFieldChange("material", event.target.value)}
      />
    </InspectorGroup>
  );
}

function ActionsSection({
  draft,
  feedback,
  onApplyCreateDraft,
  onRebaseAfterConflict,
  onRefetchAfterConflict,
  onRetryAfterConflict,
  pending,
  revisionConflictPhase,
}: {
  draft: GeometryObjectDraft;
  feedback: Feedback | null;
  onApplyCreateDraft: () => Promise<boolean>;
  onRebaseAfterConflict: () => void;
  onRefetchAfterConflict: () => void;
  onRetryAfterConflict: () => Promise<boolean>;
  pending: boolean;
  revisionConflictPhase: "conflict" | "refresh-error" | "refreshing" | "rebased" | "refetched" | null;
}) {
  return (
    <InspectorGroup title="Actions">
      <div className="fm-inspector-toolbar">
        {draft.mode === "draft-new" ? (
          <Button
            disabled={
              pending ||
              draft.baseRevision === null ||
              revisionConflictPhase !== null
            }
            size="sm"
            type="button"
            variant="primary"
            onClick={() => void onApplyCreateDraft()}
          >
            Apply Draft
          </Button>
        ) : null}
      </div>
      {feedback ? (
        <FeedbackBanner kind={feedback.kind} message={feedback.message} />
      ) : null}
      {revisionConflictPhase ? (
        <div className="fm-inspector-toolbar" data-revision-conflict="true">
          <Button
            disabled={pending || revisionConflictPhase === "refreshing"}
            size="sm"
            type="button"
            variant="ghost"
            onClick={onRefetchAfterConflict}
          >
            Refetch Scene
          </Button>
          <Button
            disabled={pending || revisionConflictPhase !== "refetched"}
            size="sm"
            type="button"
            variant="ghost"
            onClick={onRebaseAfterConflict}
          >
            Rebase Draft
          </Button>
          <Button
            disabled={pending || revisionConflictPhase !== "rebased"}
            size="sm"
            type="button"
            variant="primary"
            onClick={() => void onRetryAfterConflict()}
          >
            Retry Apply
          </Button>
        </div>
      ) : null}
    </InspectorGroup>
  );
}

function ValidationSection({
  messages,
  status,
}: {
  messages: string[];
  status: string;
}) {
  return (
    <InspectorGroup
      title="Validation"
      badge={messages.length > 0 ? String(messages.length) : undefined}
      collapsible
      defaultOpen={messages.length > 0}
    >
      <FieldRow label="Fetch state" value={status} />
      {messages.length > 0 ? (
        <ul className="fm-inspector-validation-list">
          {messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : (
        <FieldRow label="Backend validation" value="no object issues" />
      )}
    </InspectorGroup>
  );
}

function DraftVectorFormField({
  disabled,
  errors,
  label,
  onChange,
  unit,
  values,
}: {
  disabled?: boolean;
  errors?: readonly (string | undefined)[];
  label: string;
  onChange: (index: 0 | 1 | 2, value: string) => void;
  unit: string;
  values: readonly [string, string, string];
}) {
  return (
    <Vector3Field
      disabled={disabled}
      errors={errors}
      label={label}
      unit={unit}
      values={values}
      onChange={onChange}
    />
  );
}
