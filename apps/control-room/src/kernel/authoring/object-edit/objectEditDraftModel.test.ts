import { describe, expect, it } from "vitest";

import {
  geometryDraftGeometryEquals,
  geometryDraftTranslationEquals,
  resolveCommittedGeometryObjectDraft,
} from "./objectEditDraftModel";

describe("object edit draft quantity semantics", () => {
  it("treats explicit unit spellings as the same SI geometry and translation values", () => {
    const baseline = resolveCommittedGeometryObjectDraft(
      {
        objects: [{
          geometry: {
            geometry_kind: "Box",
            geometry_params: { size: [1e-7, 1e-7, 1e-8] },
          },
          id: "box",
          transform: { translation: [1e-9, 2e-9, 3e-9] },
        }],
        revision: 4,
      },
      "box",
    );
    expect(baseline).not.toBeNull();
    if (!baseline) return;

    const equivalent = {
      ...baseline,
      size: ["100 nm", "0,1 um", "10 nm"] as [string, string, string],
      translation: ["1 nm", "2 nm", "3 nm"] as [string, string, string],
    };

    expect(geometryDraftGeometryEquals(equivalent, baseline)).toBe(true);
    expect(geometryDraftTranslationEquals(equivalent, baseline)).toBe(true);
    expect(equivalent.size[0]).toBe("100 nm");
  });

  it("does not treat invalid or materially different text as a semantic no-op", () => {
    const baseline = resolveCommittedGeometryObjectDraft(
      {
        objects: [{
          geometry: {
            geometry_kind: "Box",
            geometry_params: { size: [1e-7, 1e-7, 1e-8] },
          },
          id: "box",
          transform: { translation: [0, 0, 0] },
        }],
        revision: 4,
      },
      "box",
    );
    expect(baseline).not.toBeNull();
    if (!baseline) return;

    expect(geometryDraftGeometryEquals({
      ...baseline,
      size: ["1e-7", "0.001 nm", "1e-8"],
    }, baseline)).toBe(false);
    expect(geometryDraftTranslationEquals({
      ...baseline,
      translation: ["bad", "0", "0"],
    }, baseline)).toBe(false);
  });
});
