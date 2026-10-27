"use client";

import { useSyncExternalStore } from "react";

import {
  useRegisterInspectorEditSession,
  type InspectorEditSession,
  type InspectorEditSessionStore,
} from "../InspectorEditSession";
import { combineObjectMaterialEditSessions } from "./ObjectMaterialPanelEditSession";

const emptyInspectorEditSessionVersion = () => 0;

export function ObjectMaterialPanelEditSessionBridge({
  absorbingBoundaryEditSessionStore,
  materialSession,
}: {
  absorbingBoundaryEditSessionStore: InspectorEditSessionStore;
  materialSession: InspectorEditSession;
}) {
  useSyncExternalStore(
    absorbingBoundaryEditSessionStore.subscribe,
    absorbingBoundaryEditSessionStore.getVersion,
    emptyInspectorEditSessionVersion,
  );
  const combinedEditSession = combineObjectMaterialEditSessions(
    materialSession,
    absorbingBoundaryEditSessionStore.getCurrentSession(),
  );
  useRegisterInspectorEditSession(
    combinedEditSession.mode,
    combinedEditSession.applying,
    combinedEditSession.dirty,
    combinedEditSession.valid,
    combinedEditSession.lockReason,
    combinedEditSession.apply,
    combinedEditSession.reset,
    {
      applyBlockReason: combinedEditSession.applyBlockReason,
      historyMode: "mutation-owned",
    },
  );
  return null;
}
