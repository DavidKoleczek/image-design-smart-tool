import { useSyncExternalStore } from "react";

/** What is being written for one image, or for the new image, before it is sent. */
export type Draft = {
  prompt: string;
  /** For the new image, its name as typed, without the extension; null until the person types one. */
  name: string | null;
  /**
   * For an image being edited, the size asked for; null to match the image. It is not what was picked last, since
   * an edit that quietly took the size of some other image would come out cropped or stretched.
   */
  size: [number, number] | null;
};

/** The key the new image's draft is kept under, which no image's name can be. */
export const NEW_IMAGE = "";

const EMPTY: Draft = { prompt: "", name: null, size: null };
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

/** Change what is written for the image named `key`, or for the new image. */
export function updateDraft(key: string, change: Partial<Draft>) {
  set(key, { ...(drafts.get(key) ?? EMPTY), ...change });
}

/** Give a draft to the image it now belongs to: the new image once it is created, or an image once it is renamed. */
export function moveDraft(from: string, to: string) {
  const draft = drafts.get(from);
  if (draft) {
    drafts.delete(from);
    set(to, { ...draft, name: null });
  }
}

export function useDraft(key: string): Draft {
  return useSyncExternalStore(subscribe, () => drafts.get(key) ?? EMPTY);
}
