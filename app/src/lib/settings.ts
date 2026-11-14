import { useSyncExternalStore } from "react";

import { readAppSettings, saveAppSettings, type AppSettings } from "@/lib/api";
import { keep } from "@/lib/kept";
import { setThemePreference } from "@/lib/theme";

/** `AppSettings()` in schemas.py, for when they cannot be read. */
export const DEFAULT_SETTINGS: AppSettings = {
  theme: "system",
  images_view: "details",
  advanced: false,
  wide: {
    images: { size: null, open: true },
    request: { size: null, open: true },
  },
  medium: {
    images: { size: null, open: true },
    request: { size: null, open: true },
  },
};

const store = keep<AppSettings>({
  initial: DEFAULT_SETTINGS,
  read: readAppSettings,
  save: saveAppSettings,
  what: "the settings",
  onChange: (settings) => setThemePreference(settings.theme),
});

/** Read the person's settings, before the view first paints so it opens in their theme and layout. */
export const loadSettings = store.load;

/** Change the settings at once, and save them once the person stops changing them. */
export const updateSettings = store.update;

// Another app open on this machine may have changed them, which shows here once this one gets focus.
window.addEventListener("focus", () => void store.load());

const resetListeners = new Set<() => void>();
let resets = 0;

/** Put every pane back to its default size, open. */
export function resetLayout() {
  updateSettings((current) => ({
    ...current,
    wide: DEFAULT_SETTINGS.wide,
    medium: DEFAULT_SETTINGS.medium,
  }));
  resets += 1;
  for (const listener of resetListeners) {
    listener();
  }
}

function subscribeResets(listener: () => void): () => void {
  resetListeners.add(listener);
  return () => {
    resetListeners.delete(listener);
  };
}

/** Counts layout resets, so the panes can start over from their defaults. */
export function useLayoutResets(): number {
  return useSyncExternalStore(subscribeResets, () => resets);
}

export function useSettings(): { settings: AppSettings; error: string | null } {
  const { value, error } = useSyncExternalStore(
    store.subscribe,
    store.snapshot,
  );
  return { settings: value, error };
}
