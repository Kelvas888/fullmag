export interface GeometryObjectDraft {
  archHeight: string;
  baseRevision: number | null;
  geometryKind: string;
  height: string;
  length: string;
  material: string;
  mode: "committed" | "draft-new" | "missing";
  name: string;
  notes: string;
  objectId: string;
  radius: string;
  region: string;
  rotation: [string, string, string];
  scale: [string, string, string];
  size: [string, string, string];
  translation: [string, string, string];
  width: string;
  z0: string;
}

export interface ObjectEditSessionTarget {
  objectId: string;
  sessionScopeKey: string | null;
  targetKey: string;
}

export interface ObjectEditSessionIdentity extends ObjectEditSessionTarget {
  draftId: string;
  epoch: number;
}

export interface ObjectEditSessionSnapshot<TDraft> {
  applyOperationId: number | null;
  dirty: boolean;
  draft: TDraft | null;
  editVersion: number;
  identity: ObjectEditSessionIdentity | null;
}

export interface ObjectEditApplyOperation<TDraft> {
  id: number;
  identity: ObjectEditSessionIdentity;
  submittedDraft: TDraft;
  submittedVersion: number;
}
