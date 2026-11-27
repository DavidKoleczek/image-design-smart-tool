import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  readImageActivity,
  type ImageEvent,
  type ImageRunStatus,
  type ImageSummary,
  type ImageUsage,
} from "@/lib/api";
import { poll } from "@/lib/poll";

/** What a run was asked and how it went, from its events. */
export type RunFacts = {
  id: string;
  prompt: string;
  /** The model it was sent to, when the method names one. */
  model: string | null;
  /** ISO 8601. */
  started: string;
  /** Null while it runs, and for a run whose process ended before it did. */
  finished: string | null;
  usage: ImageUsage | null;
  /** The in-progress images it has sent so far, by the index each has, oldest first. */
  previews: number[];
  /** What its `started` event says: the request, and the folder the files it names are in. */
  request: Record<string, unknown>;
  /** How it ended, once it has; null while it runs, and for a run whose process ended before it did. */
  status: ImageRunStatus | null;
  error: string | null;
  /** Each of its events, in order. */
  events: ImageEvent[];
};

export type Runs = ReadonlyMap<string, RunFacts>;

const NONE: Runs = new Map();
const listeners = new Set<() => void>();
let asked = 0;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Read every image's activity again, as after a change the listing does not show. */
export function readRunsAgain() {
  asked += 1;
  for (const listener of listeners) {
    listener();
  }
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function fold(facts: Map<string, RunFacts>, event: ImageEvent) {
  if (event.kind === "started") {
    facts.set(event.run_id, {
      id: event.run_id,
      prompt: text(event.data.prompt) ?? "",
      model: text(event.data.model),
      started: event.time,
      finished: null,
      usage: null,
      previews: [],
      request: event.data,
      status: null,
      error: null,
      events: [event],
    });
    return;
  }
  const found = facts.get(event.run_id);
  if (!found) {
    return;
  }
  const run = { ...found, events: [...found.events, event] };
  if (event.kind === "preview" && typeof event.data.index === "number") {
    facts.set(event.run_id, {
      ...run,
      previews: [...run.previews, event.data.index],
    });
  } else if (event.kind === "finished" || event.kind === "failed") {
    facts.set(event.run_id, {
      ...run,
      finished: event.time,
      usage: (event.data.usage as ImageUsage | null | undefined) ?? null,
      status: (text(event.data.status) as ImageRunStatus | null) ?? null,
      error: text(event.data.error),
    });
  } else {
    facts.set(event.run_id, run);
  }
}

/**
 * The runs on the image, by their ids in the order they started, read from its activity. It is read again, from where
 * the last read ended, each time a run starts, ends, or saves a version, and every second while a run works, for the
 * in-progress images the run sends and what its agent does.
 */
export function useRuns(image: ImageSummary | null): Runs {
  const [runs, setRuns] = useState<{
    key: string;
    facts: Map<string, RunFacts>;
  } | null>(null);
  const read = useRef<{ key: string; cursor: string | null } | null>(null);
  const again = useSyncExternalStore(subscribe, () => asked);
  const name = image?.name ?? null;
  // What has been read of an image is told by its id, which it keeps when it is renamed.
  const key = image === null ? null : (image.id ?? image.name);
  // A file the tool has made no change to has no activity to read.
  const kept =
    image !== null &&
    (image.versions.length > 0 || image.last_run !== null || !!image.design);
  const drafting = image?.drafting ?? [];
  const changed = image
    ? `${image.last_run?.id}:${image.status}:${image.versions.length}:${image.design?.run_id}:${image.design?.status}:${drafting.join(",")}:${again}`
    : "";
  const running =
    image?.status === "running" ||
    image?.design?.status === "running" ||
    drafting.length > 0;

  useEffect(() => {
    if (name === null || key === null || !kept) {
      return;
    }
    let current = true;
    // One at a time, and one dropped here is asked for again from the same place, so no event is folded twice.
    const readOn = async () => {
      const after = read.current?.key === key ? read.current.cursor : null;
      try {
        const activity = await readImageActivity(name, after);
        if (!current) {
          return;
        }
        read.current = { key, cursor: activity.cursor };
        if (activity.events.length === 0 && after !== null) {
          return;
        }
        setRuns((before) => {
          const facts = new Map(
            after !== null && before?.key === key ? before.facts : [],
          );
          for (const event of activity.events) {
            fold(facts, event);
          }
          return { key, facts };
        });
      } catch {
        // The versions show without what made them until the next read.
      }
    };
    const stop = running ? poll(readOn) : undefined;
    if (!running) {
      void readOn();
    }
    return () => {
      current = false;
      stop?.();
    };
  }, [name, key, kept, changed, running]);

  return runs?.key === key ? runs.facts : NONE;
}
