import { useSyncExternalStore } from "react";

import { movedPath } from "@/lib/paths";
import { onRenamed, rekey } from "@/lib/renames";

/** What is being written for one image, or for the new image, before it is sent. */
export type Draft = {
  prompt: string;
  /** What is being written to the agent, apart from the prompt of an image call being written by hand. */
  message: string;
  /** For the new image, its name as typed, without the extension; null until the person types one. */
  name: string | null;
  /** For the new image, the folder it goes in, "" for the top. */
  folder: string;
  /**
   * For an image being edited, the size asked for; null to match the image. It is not what was picked last, since
   * an edit that quietly took the size of some other image would come out cropped or stretched.
   */
  size: [number, number] | null;
  /**
   * For an image in view, what a request on it makes, a still image or an animation; null for what the image is. It
   * is not what was picked last either, so an image is not animated, or an animation flattened, without being asked.
   */
  kind: "image" | "animation" | null;
  /** For an animation being edited, how many frames and how long each shows; null to keep its own. */
  frames: number | null;
  frameMs: number | null;
};

// Starts the key a new image's draft is kept under, which no image's name can, since no name can have a colon.
const NEW_IMAGE = ":new-";

const EMPTY: Draft = {
  prompt: "",
  message: "",
  name: null,
  folder: "",
  size: null,
  kind: null,
  frames: null,
  frameMs: null,
};
const listeners = new Set<() => void>();
// Kept apart from the pane that shows them, so a draft outlives the pane closing and the image going out of view.
const drafts = new Map<string, Draft>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function set(key: string, draft: Draft | null) {
  if (draft === null) {
    drafts.delete(key);
  } else {
    drafts.set(key, draft);
  }
  for (const listener of listeners) {
    listener();
  }
}

/** The key the draft of a new image is kept under, by an id of its own, so several can be described at once. */
export function newImageKey(id: string): string {
  return `${NEW_IMAGE}${id}`;
}

/** Change what is written for the image named `key`, or for a new image. */
export function updateDraft(key: string, change: Partial<Draft>) {
  set(key, { ...(drafts.get(key) ?? EMPTY), ...change });
}

/** Drop what was written for a new image that will not be made. */
export function dropDraft(key: string) {
  set(key, null);
}

export function draftOf(key: string): Draft {
  return drafts.get(key) ?? EMPTY;
}

/** Give a new image's draft to the image it became once it was created. */
export function moveDraft(from: string, to: string) {
  const draft = drafts.get(from);
  if (draft) {
    drafts.delete(from);
    set(to, { ...draft, name: null });
  }
}

onRenamed((from, to) => {
  let moved = rekey(drafts, (key) => movedPath(key, from, to));
  // A new image goes in the folder it was put in under the name the folder has now.
  for (const [key, draft] of drafts) {
    const folder = movedPath(draft.folder, from, to);
    if (folder !== draft.folder) {
      drafts.set(key, { ...draft, folder });
      moved = true;
    }
  }
  if (moved) {
    for (const listener of listeners) {
      listener();
    }
  }
});

export function useDraft(key: string): Draft {
  return useSyncExternalStore(subscribe, () => drafts.get(key) ?? EMPTY);
}
