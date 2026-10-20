import { describe, expect, it, vi } from "vitest";

import {
  createViewport3DPreferencesHydrationAdapter,
  type Viewport3DPreferencesStorage,
} from "./viewport3dAppearanceHydration";
import {
  DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
  DEFAULT_VIEWPORT_3D_PERSISTED_WIDGET_PREFERENCES,
  serializeViewport3DPersistedPreferences,
  VIEWPORT_3D_APPEARANCE_PREFERENCES_STORAGE_KEY,
  type Viewport3DAppearancePreferences,
  type Viewport3DPersistedWidgetPreferences,
  type Viewport3DPersistedPreferences,
  type Viewport3DPersistedPreferencesSource,
} from "./viewport3dAppearancePreferences";

describe("viewport3dAppearanceHydration", () => {
  it("hydrates once after subscription and writes only persisted preference changes", () => {
    const camera = { position: [1, 2, 3] };
    let snapshot: Viewport3DPersistedPreferencesSource & {
      appearance: Viewport3DAppearancePreferences;
      camera: unknown;
      widgets: Viewport3DPersistedWidgetPreferences;
    } = {
      appearance: DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
      captureReturnProfileId: null,
      visualProfileId: "interactive",
      widgets: DEFAULT_VIEWPORT_3D_PERSISTED_WIDGET_PREFERENCES,
      camera,
    };
    const saved = serializeViewport3DPersistedPreferences({
      schemaVersion: 1,
      appearance: {
        ...DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
        backgroundMode: "gradient",
      },
      widgets: {
        ...DEFAULT_VIEWPORT_3D_PERSISTED_WIDGET_PREFERENCES,
        dimensionFrameDensity: "fine",
      },
      visualProfileId: "figure",
    });
    const writes: string[] = [];
    const storage: Viewport3DPreferencesStorage = {
      getItem: vi.fn((key: string) => key === VIEWPORT_3D_APPEARANCE_PREFERENCES_STORAGE_KEY ? saved : null),
      setItem: vi.fn((_key: string, value: string) => writes.push(value)),
    };
    const listeners = new Set<() => void>();
    const applyPreferences = vi.fn((preferences: Viewport3DPersistedPreferences | null) => {
      if (!preferences) return "ignored" as const;
      snapshot = {
        ...snapshot,
        appearance: preferences.appearance,
        widgets: preferences.widgets,
        visualProfileId: preferences.visualProfileId,
      };
      return "applied" as const;
    });
    const hydrate = createViewport3DPreferencesHydrationAdapter({
      applyPreferences,
      getSnapshot: () => snapshot,
      getStorage: () => storage,
      subscribe: (listener) => {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    });

    expect(snapshot.appearance).toEqual(DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES);
    hydrate();
    hydrate();

    expect(applyPreferences).toHaveBeenCalledTimes(1);
    expect(snapshot.appearance).toMatchObject({ backgroundMode: "gradient" });
    expect(snapshot.visualProfileId).toBe("figure");
    expect(snapshot.camera).toBe(camera);

    snapshot = { ...snapshot, camera: { position: [4, 5, 6] } };
    for (const listener of listeners) listener();
    expect(writes).toHaveLength(0);

    snapshot = {
      ...snapshot,
      appearance: { ...snapshot.appearance, backgroundStrength: 0.8 },
    };
    for (const listener of listeners) listener();
    expect(writes).toHaveLength(1);
    expect(JSON.parse(writes[0] ?? "{}").appearance.backgroundStrength).toBe(0.8);
    expect(JSON.parse(writes[0] ?? "{}").camera).toBeUndefined();
  });

  it("leaves the in-memory path safe when browser storage is unavailable", () => {
    const applyPreferences = vi.fn(() => "ignored" as const);
    const subscribe = vi.fn(() => () => {});
    const hydrate = createViewport3DPreferencesHydrationAdapter({
      applyPreferences,
      getSnapshot: () => ({
        appearance: DEFAULT_VIEWPORT_3D_APPEARANCE_PREFERENCES,
        captureReturnProfileId: null,
        visualProfileId: "interactive",
        widgets: DEFAULT_VIEWPORT_3D_PERSISTED_WIDGET_PREFERENCES,
      }),
      getStorage: () => null,
      subscribe,
    });

    expect(() => hydrate()).not.toThrow();
    expect(applyPreferences).not.toHaveBeenCalled();
    expect(subscribe).not.toHaveBeenCalled();
  });
});
