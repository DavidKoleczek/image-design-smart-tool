import { useSyncExternalStore } from "react";

/** The editor of an image call, open over the conversation: filled from a call made before, or written by hand. */
export type Sheet = {
  title: string;
  /** Whether it was filled from a call, so what it holds is not the person's to keep once it closes. */
  filled: boolean;
};

const listeners = new Set<() => void>();
// The editor open now, and what it was opened on, kept as drafts are; another image in view leaves it.
let open: { key: string; sheet: Sheet } | null = null;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function changed() {
  for (const listener of listeners) {
    listener();
  }
}

/** The editor open on what is kept under `key`; null when it is not open there. */
export function useSheet(key: string): Sheet | null {
  return useSyncExternalStore(subscribe, () =>
    open?.key === key ? open.sheet : null,
  );
}

export function openSheet(key: string, sheet: Sheet) {
  open = { key, sheet };
  changed();
}

export function closeSheet() {
  open = null;
  changed();
}
