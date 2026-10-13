import { describe, expect, it, vi } from "vitest";

import {
  captureRegionAuxiliaryDraftApply,
  resetRegionAggregateDraft,
} from "./ObjectRegionsPanelModel";

describe("ObjectRegionsPanel composite Apply snapshots", () => {
  it("applies only the child callback and dirty state captured at click time", async () => {
    const applied = vi.fn(async () => true);
    const childBecameDirty = vi.fn(async () => true);
    const clickedSnapshot = captureRegionAuxiliaryDraftApply({
      apply: applied,
      dirty: true,
    });
    const currentSession = {
      apply: childBecameDirty,
      dirty: true,
    };

    expect(currentSession.dirty).toBe(true);
    await clickedSnapshot.apply?.();

    expect(applied).toHaveBeenCalledOnce();
    expect(childBecameDirty).not.toHaveBeenCalled();
  });

  it("does not apply a child draft that becomes dirty after the click", async () => {
    const childApply = vi.fn(async () => true);
    const clickedSnapshot = captureRegionAuxiliaryDraftApply({
      apply: childApply,
      dirty: false,
    });

    expect(clickedSnapshot.dirty).toBe(false);
    expect(clickedSnapshot.apply).toBeNull();
    await clickedSnapshot.apply?.();
    expect(childApply).not.toHaveBeenCalled();
  });

  it("resets the child draft and then the parent draft for aggregate Revert", () => {
    const calls: string[] = [];
    resetRegionAggregateDraft(
      { reset: () => calls.push("child baseline") },
      () => calls.push("region baseline"),
    );

    expect(calls).toEqual(["child baseline", "region baseline"]);
  });
});
