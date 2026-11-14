import { useSyncExternalStore } from "react";

import { readAppState, saveAppState, type AppState } from "@/lib/api";
import { DEFAULT_SVG } from "@/lib/drawing";
import { movedFile } from "@/lib/images";
import { keep } from "@/lib/kept";
import { movedPath } from "@/lib/paths";
import { onRenamed } from "@/lib/renames";
import { DEFAULT_REQUEST } from "@/lib/request";

/** `AppState()` in schemas.py, for when it cannot be read. */
const DEFAULT_STATE: AppState = {
  method: "model",
  request: DEFAULT_REQUEST,
  svg: DEFAULT_SVG,
  closed_folders: [],
  pins: [],
  folders: [],
};

const store = keep<AppState>({
  initial: DEFAULT_STATE,
  read: readAppState,
  save: saveAppState,
  what: "what you picked here",
});
let followed: string | null = null;

/** Read what the person last picked for the images in the app's directory, before the view first paints. */
export const loadAppState = store.load;

/** Change what is picked at once, and save it for the app's directory once the person stops changing it. */
export const updateAppState = store.update;

/** Save a change still waiting, and wait until the server has it. */
export const flushAppState = store.flush;

// A folder stays open or closed, and a pin stays on its file, under the name each has now. The server moves the
// pins it keeps as well, and these are the view's own copy, which the next save would put back as they were.
onRenamed((from, to) => {
  const { closed_folders, pins } = store.snapshot().value;
  const closed = closed_folders.map((folder) => movedPath(folder, from, to));
  const pinned = pins.map((pin) => movedFile(pin, from, to));
  if (
    closed.some((folder, index) => folder !== closed_folders[index]) ||
    pinned.some((pin, index) => pin !== pins[index])
  ) {
    store.update((current) => ({
      ...current,
      closed_folders: closed,
      pins: pinned,
    }));
  }
});

/** What is picked now, for an effect that changes it only when it differs. */
export function appStateNow(): AppState {
  return store.snapshot().value;
}

/** Read it again once the app shows another directory, whose picks are its own. */
export function followDirectory(dataDirectory: string | null) {
  if (dataDirectory === null || dataDirectory === followed) {
    return;
  }
  const switched = followed !== null;
  followed = dataDirectory;
  if (switched) {
    void store.moved();
  }
}

export function useAppState(): { state: AppState; error: string | null } {
  const { value, error } = useSyncExternalStore(
    store.subscribe,
    store.snapshot,
  );
  return { state: value, error };
}
