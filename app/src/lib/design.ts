import type { ImageMethods } from "@/lib/api";
import { updateDraft } from "@/lib/drafts";
import { addEntries, clearReferences, entryOf } from "@/lib/references";
import { CHATGPT } from "@/lib/request";
import { updateAppState } from "@/lib/state";
import type { ImageCall } from "@/lib/thread";

function pair(value: string | undefined): [number, number] | null {
  const [width, height] = (value ?? "").split("x").map(Number);
  return Number.isInteger(width) && Number.isInteger(height)
    ? [width, height]
    : null;
}

/**
 * Fill the request being written by hand for `key` from an image call, so the editor opens on what the call sends:
 * its prompt, its references, and the model and output options it set.
 */
export function fillEditor(
  key: string,
  call: ImageCall,
  methods: ImageMethods,
) {
  const set = new Map(call.parameters);
  updateDraft(key, {
    prompt: call.prompt,
    ...(call.edits ? { size: pair(set.get("size")) } : {}),
  });
  clearReferences(key);
  addEntries(
    key,
    call.images
      .filter((image) => image.role === "reference")
      .map((image) => entryOf(image.path)),
    Infinity,
  );
  updateAppState((current) => ({
    ...current,
    request: {
      ...current.request,
      model: call.method === "chatgpt" ? CHATGPT : call.model,
      quality: set.get("quality") ?? "auto",
      complexity:
        set.get("complexity") &&
        methods.openai.complexities.includes(set.get("complexity") ?? "")
          ? (set.get("complexity") ?? null)
          : null,
      background: set.get("background") ?? "auto",
    },
  }));
}
