export type MoveAxis = "x" | "y" | "z";
export type Translation3 = [number, number, number];

export interface MoveCommitLockToken {
  lockHeldByGesture: true;
}

export type MoveCommitHandler = (
  objectId: string,
  translation: Translation3,
  baseRevision: number,
  lock?: MoveCommitLockToken,
) => Promise<boolean | void> | boolean | void;

const pendingMoveCommits = new WeakSet<MoveCommitHandler>();

export function isMoveCommitPending(handler: MoveCommitHandler): boolean {
  return pendingMoveCommits.has(handler);
}

export function tryAcquireMoveCommit(
  handler: MoveCommitHandler,
): (() => void) | null {
  if (pendingMoveCommits.has(handler)) return null;
  pendingMoveCommits.add(handler);
  return () => pendingMoveCommits.delete(handler);
}
