import { describe, expect, it } from "vitest";

import { ObjectEditSessionController } from "./ObjectEditSessionController";

describe("ObjectEditSessionController", () => {
  it("does not admit a late ACK into a later A-to-B-to-A selection epoch", () => {
    const controller = new ObjectEditSessionController<{ value: number }>();
    const targetA = {
      objectId: "object-a",
      sessionScopeKey: "session-a",
      targetKey: "object.geometry:object-a",
    };
    const identityA1 = controller.activate(targetA, { value: 1 });
    const operation = controller.beginApply(identityA1);
    expect(operation).not.toBeNull();

    controller.activate({
      objectId: "object-b",
      sessionScopeKey: "session-a",
      targetKey: "object.geometry:object-b",
    }, { value: 20 });
    const identityA3 = controller.activate(targetA, { value: 3 });

    expect(identityA3.epoch).toBeGreaterThan(identityA1.epoch);
    expect(controller.acknowledge(
      operation!,
      { value: 2 },
      (_current, _submitted, canonical) => ({ dirty: false, draft: canonical }),
    )).toBe(false);
    expect(controller.getSnapshot()).toMatchObject({
      draft: { value: 3 },
      identity: identityA3,
    });
  });

  it("keeps edits made after Apply while adopting the acknowledged baseline", () => {
    const controller = new ObjectEditSessionController<{ value: number }>();
    const identity = controller.activate({
      objectId: "object-a",
      sessionScopeKey: "session-a",
      targetKey: "object.geometry:object-a",
    }, { value: 0 });
    controller.updateDraft(identity, () => ({ value: 1 }));
    const operation = controller.beginApply(identity)!;
    controller.updateDraft(identity, () => ({ value: 2 }));

    expect(controller.acknowledge(
      operation,
      { value: 1 },
      (currentDraft, submittedDraft, canonicalDraft) => ({
        dirty: currentDraft.value !== canonicalDraft.value,
        draft: currentDraft.value !== submittedDraft.value
          ? currentDraft
          : canonicalDraft,
      }),
    )).toBe(true);
    expect(controller.getSnapshot()).toMatchObject({
      applyOperationId: null,
      dirty: true,
      draft: { value: 2 },
    });
  });

  it("releases session-scoped serialization after the session is cleared", () => {
    const controller = new ObjectEditSessionController<{ value: number }>();
    const target = {
      objectId: "object-a",
      sessionScopeKey: "session-a",
      targetKey: "object.geometry:object-a",
    };
    const oldIdentity = controller.activate(target, { value: 0 });
    const oldOperation = controller.beginApply(oldIdentity)!;

    controller.clear();
    const newIdentity = controller.activate(target, { value: 1 });

    expect(controller.beginApply(newIdentity)).not.toBeNull();
    expect(controller.acknowledge(
      oldOperation,
      { value: -1 },
      (_current, _submitted, canonical) => ({ dirty: false, draft: canonical }),
    )).toBe(false);
    expect(controller.getSnapshot()).toMatchObject({
      draft: { value: 1 },
      identity: newIdentity,
    });
  });
});
