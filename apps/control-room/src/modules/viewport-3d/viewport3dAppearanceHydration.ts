import {
  buildViewport3DPersistedPreferences,
  parseViewport3DPersistedPreferences,
  serializeViewport3DPersistedPreferences,
  VIEWPORT_3D_APPEARANCE_PREFERENCES_STORAGE_KEY,
  type Viewport3DPersistedPreferences,
  type Viewport3DPersistedPreferencesSource,
} from "./viewport3dAppearancePreferences";

export interface Viewport3DPreferencesStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export type Viewport3DPreferencesHydrationResult =
  | "applied"
  | "local-changes"
  | "ignored";

export interface Viewport3DPreferencesHydrationAdapterOptions {
  getSnapshot(): Viewport3DPersistedPreferencesSource;
  applyPreferences(
    preferences: Viewport3DPersistedPreferences | null,
  ): Viewport3DPreferencesHydrationResult;
  subscribe(listener: () => void): () => void;
  getStorage(): Viewport3DPreferencesStorage | null;
}

/**
 * Read preferences only after the browser store is subscribed. SSR and the
 * first hydrated render therefore keep their fixed default snapshot.
 */
export function createViewport3DPreferencesHydrationAdapter({
  applyPreferences,
  getSnapshot,
  getStorage,
  subscribe,
}: Viewport3DPreferencesHydrationAdapterOptions): () => void {
  let started = false;

  return () => {
    if (started) return;
    started = true;

    const storage = safelyGetStorage(getStorage);
    if (!storage) return;

    let serialized: string | null = null;
    try {
      serialized = storage.getItem(VIEWPORT_3D_APPEARANCE_PREFERENCES_STORAGE_KEY);
    } catch {
      // A blocked browser storage implementation leaves in-memory defaults usable.
    }

    const persisted = parseViewport3DPersistedPreferences(serialized);
    const hydrationResult = applyPreferences(persisted);
    let lastSerialized = serializeCurrentPreferences(getSnapshot());

    if (hydrationResult === "local-changes" && lastSerialized !== null) {
      safelyWrite(storage, lastSerialized);
    }

    subscribe(() => {
      const nextSerialized = serializeCurrentPreferences(getSnapshot());
      if (nextSerialized === null || nextSerialized === lastSerialized) return;
      if (safelyWrite(storage, nextSerialized)) {
        lastSerialized = nextSerialized;
      }
    });
  };
}

export function getViewport3DBrowserPreferencesStorage(): Viewport3DPreferencesStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function serializeCurrentPreferences(
  snapshot: Viewport3DPersistedPreferencesSource,
): string | null {
  const preferences = buildViewport3DPersistedPreferences(snapshot);
  return preferences ? serializeViewport3DPersistedPreferences(preferences) : null;
}

function safelyGetStorage(
  getStorage: () => Viewport3DPreferencesStorage | null,
): Viewport3DPreferencesStorage | null {
  try {
    return getStorage();
  } catch {
    return null;
  }
}

function safelyWrite(
  storage: Viewport3DPreferencesStorage,
  serialized: string,
): boolean {
  try {
    storage.setItem(VIEWPORT_3D_APPEARANCE_PREFERENCES_STORAGE_KEY, serialized);
    return true;
  } catch {
    return false;
  }
}
