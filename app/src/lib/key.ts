import { useSyncExternalStore } from "react";

import {
  clearOpenAIKey,
  enterOpenAIKey,
  readOpenAIKey,
  type OpenAIKeyStatus,
} from "@/lib/api";
import { loadMethods } from "@/lib/methods";

type KeyState = {
  /** Whether the dialog about the key shows. */
  open: boolean;
  /** Where the key comes from; null until it is read. The key itself never reaches the view. */
  status: OpenAIKeyStatus | null;
};

const listeners = new Set<() => void>();
let state: KeyState = { open: false, status: null };

function set(change: Partial<KeyState>) {
  state = { ...state, ...change };
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useKey(): KeyState {
  return useSyncExternalStore(subscribe, () => state);
}

/** Read where the OpenAI API key comes from on the machine the server runs on. */
export async function loadKey() {
  try {
    set({ status: await readOpenAIKey() });
  } catch {
    // What shows stands in until the next read.
  }
}

export function openKeyDialog() {
  set({ open: true });
  void loadKey();
}

export function closeKeyDialog() {
  set({ open: false });
}

/**
 * Have the person type the key into a window on the machine the server runs on, which saves it there. Returns whether
 * they entered one. What the models can do is read again, since a key sets the OpenAI API up.
 */
export async function enterKey(): Promise<boolean> {
  const { entered, ...status } = await enterOpenAIKey();
  set({ status });
  await loadMethods();
  return entered;
}

/** Forget the saved key. */
export async function clearKey(): Promise<void> {
  set({ status: await clearOpenAIKey() });
  await loadMethods();
}
