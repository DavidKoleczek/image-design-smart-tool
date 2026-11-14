import { useEffect, useRef, useState } from "react";

import {
  readImageActivity,
  type ImageEvent,
  type ImageSummary,
  type ImageUsage,
} from "@/lib/api";

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
};

export type Runs = ReadonlyMap<string, RunFacts>;

const NONE: Runs = new Map();

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
    });
    return;
  }
  const run = facts.get(event.run_id);
  if (run && (event.kind === "finished" || event.kind === "failed")) {
    facts.set(event.run_id, {
      ...run,
      finished: event.time,
      usage: (event.data.usage as ImageUsage | null | undefined) ?? null,
    });
  }
}

/**
 * The runs on the image, by their ids, read from its activity. It is read again, from where the last read ended, each
 * time a run starts, ends, or saves a version.
 */
export function useRuns(image: ImageSummary | null): Runs {
  const [runs, setRuns] = useState<{
    name: string;
    facts: Map<string, RunFacts>;
  } | null>(null);
  const read = useRef<{ name: string; cursor: string | null } | null>(null);
  const name = image?.name ?? null;
  // A file the tool has made no change to has no activity to read.
  const kept =
    image !== null && (image.versions.length > 0 || image.last_run !== null);
  const changed = image
    ? `${image.last_run?.id}:${image.status}:${image.versions.length}`
    : "";

  useEffect(() => {
    if (name === null || !kept) {
      return;
    }
    let current = true;
    const after = read.current?.name === name ? read.current.cursor : null;
    readImageActivity(name, after).then(
      (activity) => {
        if (!current) {
          return;
        }
        read.current = { name, cursor: activity.cursor };
        setRuns((before) => {
          const facts = new Map(
            after !== null && before?.name === name ? before.facts : [],
          );
          for (const event of activity.events) {
            fold(facts, event);
          }
          return { name, facts };
        });
      },
      () => {
        // The versions show without what made them until the next read.
      },
    );
    return () => {
      current = false;
    };
  }, [name, kept, changed]);

  return runs?.name === name ? runs.facts : NONE;
}
