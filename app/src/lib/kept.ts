import { describe } from "@/lib/errors";

const SAVE_DELAY_MS = 400;

export type Kept<Value> = { value: Value; error: string | null };

/**
 * Something the server keeps for the person: it changes here at once, is saved once they stop changing it, and is read
 * again when asked, unless a change is on its way out.
 */
export function keep<Value>(options: {
  initial: Value;
  read: () => Promise<Value>;
  save: (value: Value) => Promise<Value>;
  /** Names it in the notice when it cannot be saved, such as "the settings". */
  what: string;
  /** Called with each value as it takes effect. */
  onChange?: (value: Value) => void;
}) {
  const listeners = new Set<() => void>();
  let state: Kept<Value> = { value: options.initial, error: null };
  let timer: ReturnType<typeof setTimeout> | undefined;
  // Changed here and not yet saved, or being saved: a read meanwhile would undo the change.
  let unsaved = false;
  let saving = 0;
  // Counts the times the server came to keep it somewhere else, so an answer from the place before is dropped.
  let place = 0;

  const set = (next: Kept<Value>) => {
    state = next;
    options.onChange?.(next.value);
    for (const listener of listeners) {
      listener();
    }
  };

  const load = async () => {
    const asked = place;
    try {
      const value = await options.read();
      if (!unsaved && saving === 0 && asked === place) {
        set({ ...state, value });
      }
    } catch {
      // What shows stands in until the next read.
    }
  };

  const save = async () => {
    unsaved = false;
    saving += 1;
    try {
      await options.save(state.value);
      if (state.error) {
        set({ ...state, error: null });
      }
    } catch (cause) {
      set({
        ...state,
        error: `Could not save ${options.what}. ${describe(cause)}`,
      });
    } finally {
      saving -= 1;
    }
  };

  // A change made just before the view goes away is saved now rather than lost with the timer.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && unsaved) {
      clearTimeout(timer);
      void save();
    }
  });

  return {
    load,
    /** Change it at once, and save it once the person stops changing it. */
    update(change: (current: Value) => Value) {
      set({ ...state, value: change(state.value) });
      unsaved = true;
      clearTimeout(timer);
      timer = setTimeout(() => void save(), SAVE_DELAY_MS);
    },
    /** Read it from where the server keeps it now. A change not yet saved was for the place before, and is dropped. */
    moved() {
      clearTimeout(timer);
      unsaved = false;
      place += 1;
      return load();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    snapshot: () => state,
  };
}
