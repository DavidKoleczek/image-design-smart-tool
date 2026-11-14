import type { ImageListing } from "@/lib/api";
import type { Target } from "@/lib/request";
import type { Runs } from "@/lib/runs";

/** A prompt a request can start from, with what it was for and when it was sent. */
export type EarlierPrompt = {
  key: string;
  tag: string;
  when: string;
  text: string;
};

/** The prompts a request can start from: those of the image's versions, newest first, or each image's last. */
export function earlierPrompts(
  target: Target,
  runs: Runs,
  listing: ImageListing | null,
): EarlierPrompt[] {
  const prompts: EarlierPrompt[] = [];
  const seen = new Set<string>();
  const add = (prompt: EarlierPrompt) => {
    if (prompt.text.trim() && !seen.has(prompt.text)) {
      seen.add(prompt.text);
      prompts.push(prompt);
    }
  };
  if (target.image) {
    for (const version of [...target.image.versions].reverse()) {
      const run = version.run_id !== null ? runs.get(version.run_id) : null;
      if (run) {
        add({
          key: version.id,
          tag: version.id,
          when: version.created,
          text: run.prompt,
        });
      }
    }
  } else {
    for (const image of listing?.images ?? []) {
      if (image.last_run) {
        add({
          key: image.name,
          tag: image.name,
          when: image.last_run.started,
          text: image.last_run.prompt,
        });
      }
    }
  }
  return prompts;
}
