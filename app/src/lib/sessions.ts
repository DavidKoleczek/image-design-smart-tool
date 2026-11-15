import { useSyncExternalStore } from "react";

import { providerLabel } from "@/lib/drawing";
import { movedPath } from "@/lib/paths";
import { onRenamed, rekey } from "@/lib/renames";

/** Whether the next request on an image continues the agent session that last worked on it, and why or why not. */
export type Session = {
  /** Whether there is a session the agent picked can go on with. */
  continuable: boolean;
  continuing: boolean;
  hint: string;
};

const listeners = new Set<() => void>();
// The images Continue session was switched on or off for, kept for the session. The rest continue.
const resumes = new Map<string, boolean>();

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

/** Whether Continue session is on for the image. */
export function useResume(name: string): boolean {
  return useSyncExternalStore(subscribe, () => resumes.get(name) ?? true);
}

export function setResume(name: string, resume: boolean) {
  resumes.set(name, resume);
  changed();
}

onRenamed((from, to) => {
  if (rekey(resumes, (name) => movedPath(name, from, to))) {
    changed();
  }
});

/**
 * Whether the next request continues the image's last agent session, given the agent provider that session ran on
 * (null for none), the agent provider picked, and whether Continue session is on. `reads` is what a fresh session
 * starts from.
 */
export function sessionOf(
  ranOn: string | null,
  provider: string,
  resume: boolean,
  reads: string,
): Session {
  // A session goes on only with the agent provider it ran on.
  const continuable = ranOn !== null && ranOn === provider;
  const continuing = resume && continuable;
  const fresh = `so this starts a fresh session, which reads ${reads}`;
  const hint =
    ranOn === null
      ? `It has no agent session yet, ${fresh}`
      : !continuable
        ? `Its last session ran on ${providerLabel(ranOn)}, which this agent can't continue, ${fresh}. Pick a ${providerLabel(ranOn)} agent to continue it.`
        : continuing
          ? "Continues the agent session that last worked on it, which remembers the conversation"
          : `Starts a fresh agent session, which reads ${reads}`;
  return { continuable, continuing, hint };
}
