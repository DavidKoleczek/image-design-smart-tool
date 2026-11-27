import { useEffect, useState, useSyncExternalStore } from "react";

import { viewImage, type ImageSummary } from "@/lib/api";
import { useGuides, type CanvasMode } from "@/lib/canvas";
import { movedPath } from "@/lib/paths";
import type { Picture } from "@/lib/pictures";
import { onRenamed, rekey } from "@/lib/renames";
import type { Shown } from "@/lib/viewed";

/** How the animation in view is being looked at: the frame that shows, and whether it plays. */
export type Playback = { frame: number; playing: boolean };

// A frame said to show for this long or less is shown for the time below instead, as browsers do with a GIF's.
const TOO_SHORT_MS = 10;
const SHORT_FRAME_MS = 100;
const STILL: Playback = { frame: 0, playing: false };

const listeners = new Set<() => void>();
// How each image is being looked at, and what of it that was said of, so it starts over when the image shows
// something else.
const playbacks = new Map<string, Playback & { key: string }>();
let loop = true;
// How long each frame of a file shows, by what tells its content from any other, read once.
const durations = new Map<string, Promise<number[]>>();

function emit() {
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

onRenamed((from, to) => {
  if (rekey(playbacks, (name) => movedPath(name, from, to))) {
    emit();
  }
});

/**
 * Forget how each image was being looked at, for a workspace shown next. How long frames show stays, kept by what
 * tells a file's content from any other.
 */
export function forgetPlayback() {
  playbacks.clear();
  emit();
}

function change(name: string, next: Partial<Playback>) {
  const current = playbacks.get(name);
  if (current) {
    playbacks.set(name, { ...current, ...next });
    emit();
  }
}

/**
 * How the image named `name` is being looked at, as what it shows now, which `key` tells from anything else it could
 * show. An animation plays when it comes into view, as it does anywhere else, from its first frame.
 */
export function usePlayback(
  name: string,
  key: string | null,
  animated: boolean,
): Playback {
  useEffect(() => {
    if (key !== null && playbacks.get(name)?.key !== key) {
      playbacks.set(name, { key, frame: 0, playing: animated });
      emit();
    }
  }, [name, key, animated]);
  const kept = useSyncExternalStore(
    subscribe,
    () => playbacks.get(name) ?? STILL,
  );
  return "key" in kept && kept.key === key ? kept : STILL;
}

/** Show a frame of the image and hold it there, as when it is picked or stepped to. */
export function showFrame(name: string, frame: number) {
  change(name, { frame, playing: false });
}

/** Move on to a frame of an image that is playing. */
export function playFrame(name: string, frame: number) {
  if (playbacks.get(name)?.playing) {
    change(name, { frame });
  }
}

export function pausePlayback(name: string) {
  if (playbacks.get(name)?.playing) {
    change(name, { playing: false });
  }
}

/** Play the image, or hold it on the frame that shows. One held on its last frame with no loop plays from the start. */
export function togglePlayback(name: string, last: number) {
  const current = playbacks.get(name);
  if (!current) {
    return;
  }
  change(
    name,
    current.playing
      ? { playing: false }
      : {
          playing: true,
          frame: current.frame >= last && !loop ? 0 : current.frame,
        },
  );
}

export function useLoop(): boolean {
  return useSyncExternalStore(subscribe, () => loop);
}

export function setLoop(next: boolean) {
  loop = next;
  emit();
}

/**
 * How long each frame of an animation shows, in milliseconds, in order; null until it is read, and for an image that
 * is not an animation.
 */
export function useDurations(
  picture: Picture | null,
  animated: boolean,
): number[] | null {
  const [read, setRead] = useState<{ key: string; durations: number[] } | null>(
    null,
  );
  const key = animated ? (picture?.key ?? null) : null;
  const name = picture?.name ?? null;
  const version = picture?.version ?? null;

  useEffect(() => {
    if (key === null || name === null) {
      return;
    }
    let current = true;
    let reading = durations.get(key);
    if (!reading) {
      reading = viewImage(name, version).then(({ viewed }) =>
        (viewed?.frames ?? []).map(({ duration_ms }) =>
          duration_ms <= TOO_SHORT_MS ? SHORT_FRAME_MS : duration_ms,
        ),
      );
      durations.set(key, reading);
      // A failed read is tried again next time.
      reading.catch(() => durations.delete(key));
    }
    reading.then(
      (found) => current && setRead({ key, durations: found }),
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, [key, name, version]);

  return read !== null && read.key === key ? read.durations : null;
}

/**
 * The frame of the animation in view that a request sends: the one its marks are on, else the one it is held on, and
 * the first while it plays. Null when what shows is not an animation.
 */
export function useSourceFrame(
  image: ImageSummary | null,
  shown: Shown | null,
  mode: CanvasMode | null,
): number | null {
  const name = image?.name ?? "";
  const key = shown?.picture?.key ?? null;
  const animated = shown !== null && shown.frames > 1 && key !== null;
  // The frame alone, so what reads it is not drawn again for each frame of an animation that plays.
  const held = useSyncExternalStore(subscribe, () => {
    const kept = playbacks.get(name);
    return kept && kept.key === key && !kept.playing ? kept.frame : 0;
  });
  const guides = useGuides(name, key);
  if (!animated) {
    return null;
  }
  if (mode === "markup" && guides.marks.length > 0 && guides.frame !== null) {
    return guides.frame;
  }
  return Math.min(held, shown.frames - 1);
}
