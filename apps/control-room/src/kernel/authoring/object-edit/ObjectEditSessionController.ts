import type {
  ObjectEditApplyOperation,
  ObjectEditSessionIdentity,
  ObjectEditSessionSnapshot,
  ObjectEditSessionTarget,
} from "./objectEditTypes";

type Listener = () => void;

const EMPTY_SNAPSHOT: ObjectEditSessionSnapshot<never> = Object.freeze({
  applyOperationId: null,
  dirty: false,
  draft: null,
  editVersion: 0,
  identity: null,
});

export class ObjectEditSessionController<TDraft> {
  private listeners = new Set<Listener>();
  private draftSequence = 0;
  private epochSequence = 0;
  private operationSequence = 0;
  private pendingOperations = new Map<
    string,
    ObjectEditApplyOperation<TDraft>
  >();
  private pendingOperationKey(target: { sessionScopeKey: string | null; objectId?: string | null }): string {
    const scope = target.sessionScopeKey ?? "default";
    return target.objectId ? `${scope}:${target.objectId}` : scope;
  }
  private snapshot: ObjectEditSessionSnapshot<TDraft> = EMPTY_SNAPSHOT;

  readonly getSnapshot = (): ObjectEditSessionSnapshot<TDraft> => this.snapshot;
  readonly getServerSnapshot = (): ObjectEditSessionSnapshot<TDraft> =>
    EMPTY_SNAPSHOT as ObjectEditSessionSnapshot<TDraft>;

  readonly subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  activate(
    target: ObjectEditSessionTarget,
    initialDraft: TDraft,
  ): ObjectEditSessionIdentity {
    const current = this.snapshot.identity;
    if (
      current &&
      current.targetKey === target.targetKey &&
      current.objectId === target.objectId &&
      current.sessionScopeKey === target.sessionScopeKey
    ) {
      return current;
    }

    const identity: ObjectEditSessionIdentity = Object.freeze({
      ...target,
      draftId: "object-edit-" + String(++this.draftSequence),
      epoch: ++this.epochSequence,
    });
    this.publish({
      applyOperationId: this.pendingOperations.get(this.pendingOperationKey(target))?.id ?? null,
      dirty: false,
      draft: initialDraft,
      editVersion: 0,
      identity,
    });
    return identity;
  }

  updateDraft(
    identity: ObjectEditSessionIdentity,
    update: (draft: TDraft) => TDraft,
  ): boolean {
    if (!this.matches(identity) || this.snapshot.draft === null) return false;
    const draft = update(this.snapshot.draft);
    if (Object.is(draft, this.snapshot.draft)) return true;
    this.publish({
      ...this.snapshot,
      dirty: true,
      draft,
      editVersion: this.snapshot.editVersion + 1,
    });
    return true;
  }

  refreshCanonical(identity: ObjectEditSessionIdentity, canonicalDraft: TDraft): boolean {
    if (
      !this.matches(identity) ||
      this.snapshot.dirty ||
      this.pendingOperations.has(this.pendingOperationKey(identity)) ||
      Object.is(this.snapshot.draft, canonicalDraft)
    ) {
      return this.matches(identity);
    }
    this.publish({ ...this.snapshot, draft: canonicalDraft });
    return true;
  }

  setDirty(identity: ObjectEditSessionIdentity, dirty: boolean): boolean {
    if (!this.matches(identity) || this.snapshot.dirty === dirty) {
      return this.matches(identity);
    }
    this.publish({ ...this.snapshot, dirty });
    return true;
  }

  beginApply(
    identity: ObjectEditSessionIdentity,
  ): ObjectEditApplyOperation<TDraft> | null {
    if (
      !this.matches(identity) ||
      this.snapshot.draft === null ||
      this.pendingOperations.has(this.pendingOperationKey(identity))
    ) {
      return null;
    }
    const operation: ObjectEditApplyOperation<TDraft> = Object.freeze({
      id: ++this.operationSequence,
      identity,
      submittedDraft: this.snapshot.draft,
      submittedVersion: this.snapshot.editVersion,
    });
    this.pendingOperations.set(this.pendingOperationKey(identity), operation);
    this.publish({ ...this.snapshot, applyOperationId: operation.id });
    return operation;
  }

  acknowledge(
    operation: ObjectEditApplyOperation<TDraft>,
    canonicalDraft: TDraft,
    reconcile: (
      currentDraft: TDraft,
      submittedDraft: TDraft,
      canonicalDraft: TDraft,
    ) => { dirty: boolean; draft: TDraft },
  ): boolean {
    const opKey = this.pendingOperationKey(operation.identity);
    const pending = this.pendingOperations.get(opKey);
    const ownsPending = pending?.id === operation.id;
    if (ownsPending) {
      this.pendingOperations.delete(opKey);
    }
    const ownsCurrentDraft =
      this.matches(operation.identity) &&
      this.snapshot.applyOperationId === operation.id &&
      this.snapshot.draft !== null;
    if (!ownsCurrentDraft) {
      if (
        ownsPending &&
        this.snapshot.identity?.sessionScopeKey === operation.identity.sessionScopeKey &&
        this.snapshot.applyOperationId === operation.id
      ) {
        this.publish({ ...this.snapshot, applyOperationId: null });
      }
      return false;
    }
    const reconciled =
      this.snapshot.editVersion === operation.submittedVersion
        ? { dirty: false, draft: canonicalDraft }
        : reconcile(
            this.snapshot.draft as TDraft,
            operation.submittedDraft,
            canonicalDraft,
          );
    this.publish({
      ...this.snapshot,
      applyOperationId: null,
      dirty: reconciled.dirty,
      draft: reconciled.draft,
    });
    return true;
  }

  reject(operation: ObjectEditApplyOperation<TDraft>): boolean {
    const opKey = this.pendingOperationKey(operation.identity);
    const pending = this.pendingOperations.get(opKey);
    const ownsPending = pending?.id === operation.id;
    if (ownsPending) {
      this.pendingOperations.delete(opKey);
    }
    const ownsCurrentDraft =
      this.matches(operation.identity) &&
      this.snapshot.applyOperationId === operation.id;
    if (
      ownsPending &&
      this.snapshot.identity?.sessionScopeKey === operation.identity.sessionScopeKey &&
      this.snapshot.applyOperationId === operation.id
    ) {
      this.publish({ ...this.snapshot, applyOperationId: null });
    }
    return ownsCurrentDraft;
  }

  reset(identity: ObjectEditSessionIdentity, initialDraft: TDraft): boolean {
    if (
      !this.matches(identity) ||
      this.pendingOperations.has(this.pendingOperationKey(identity))
    ) {
      return false;
    }
    this.publish({
      applyOperationId: null,
      dirty: false,
      draft: initialDraft,
      editVersion: this.snapshot.editVersion + 1,
      identity: this.snapshot.identity,
    });
    return true;
  }

  clear(): void {
    this.epochSequence += 1;
    this.pendingOperations.clear();
    if (this.snapshot.identity === null && this.snapshot.draft === null) return;
    this.publish(EMPTY_SNAPSHOT as ObjectEditSessionSnapshot<TDraft>);
  }

  isCurrent(identity: ObjectEditSessionIdentity): boolean {
    return this.matches(identity);
  }

  private matches(identity: ObjectEditSessionIdentity): boolean {
    const current = this.snapshot.identity;
    return Boolean(
      current &&
        current.targetKey === identity.targetKey &&
        current.objectId === identity.objectId &&
        current.sessionScopeKey === identity.sessionScopeKey &&
        current.epoch === identity.epoch &&
        current.draftId === identity.draftId,
    );
  }

  private publish(snapshot: ObjectEditSessionSnapshot<TDraft>): void {
    this.snapshot = Object.freeze(snapshot);
    this.listeners.forEach((listener) => listener());
  }
}
