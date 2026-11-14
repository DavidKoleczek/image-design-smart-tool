import { useSyncExternalStore } from "react";

import { listImageMethods, type ImageMethods } from "@/lib/api";
import { describe } from "@/lib/errors";

type Read = { methods: ImageMethods | null; error: string | null };

const listeners = new Set<() => void>();
let state: Read = { methods: null, error: null };

/** Read what each way of making an image takes, and whether it is set up on the machine the server runs on. */
export async function loadMethods() {
  try {
    state = { methods: await listImageMethods(), error: null };
  } catch (cause) {
    state = {
      ...state,
      error: `Could not read what the image models take. ${describe(cause)}`,
    };
  }
  for (const listener of listeners) {
    listener();
  }
}

// Something set up since, such as a sign-in, shows once the app gets focus again.
window.addEventListener("focus", () => void loadMethods());

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useMethods(): Read {
  return useSyncExternalStore(subscribe, () => state);
}
