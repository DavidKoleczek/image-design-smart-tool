import { useSyncExternalStore } from "react";

import {
  readConfig,
  updateConfig,
  type ImageDesignConfig,
  type ImageMethods,
} from "@/lib/api";
import { keep } from "@/lib/kept";
import { loadMethods } from "@/lib/methods";

const store = keep<ImageDesignConfig>({
  initial: { design_image_models: [] },
  read: readConfig,
  save: async (config) => {
    const kept = await updateConfig(config);
    // The model the agent is given by default goes by the order, and the methods say which that is.
    await loadMethods();
    return kept;
  },
  what: "the order of the image models",
});

/** Read the person's defaults for the tool. */
export const loadConfig = store.load;

/** Change the person's defaults at once, and save them once the person stops changing them. */
export const changeConfig = store.update;

// Another app, or `image-design config`, may have changed them, which shows here once this one gets focus.
window.addEventListener("focus", () => void store.load());

export function useConfig(): {
  config: ImageDesignConfig;
  error: string | null;
} {
  const { value, error } = useSyncExternalStore(
    store.subscribe,
    store.snapshot,
  );
  return { config: value, error };
}

/**
 * Every image model the agent can be given, in the order one is picked when none is: those the config lists, then the
 * rest in the order the server gave, which is the order as last saved.
 */
export function imageModelOrder(
  config: ImageDesignConfig,
  methods: ImageMethods,
): string[] {
  const offered = methods.design.image_models;
  return [
    ...new Set([
      ...config.design_image_models.filter((model) => offered.includes(model)),
      ...offered,
    ]),
  ];
}
