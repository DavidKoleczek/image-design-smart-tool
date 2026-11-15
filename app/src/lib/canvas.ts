import { useEffect, useSyncExternalStore } from "react";

import type { Mark, MarkColor, NewMark } from "@/lib/marks";
import { movedPath } from "@/lib/paths";
import { onRenamed, rekey } from "@/lib/renames";

/**
 * What the canvas is for: marks and the mask are two ways to guide a request, and one shows at a time. Each tab has
 * its own.
 */
export type CanvasMode = "markup" | "mask";

export type Tool =
  "select" | "pan" | "circle" | "box" | "arrow" | "sketch" | "brush" | "eraser";

export const MARK_TOOLS = ["circle", "box", "arrow", "sketch"] as const;
const MASK_TOOLS: Tool[] = ["brush", "eraser"];

export const BRUSH = { min: 8, max: 256, step: 4 };
// The longest side the mask is painted at. A larger image's mask is scaled up to it when it is sent.
const MASK_EDGE = 2048;
// What the mask is painted in, under the canvas's own opacity.
const MASK_INK = "#f06e64";
// Every how many pixels the painted share is sampled.
const SAMPLE = 4;

type CanvasState = {
  tool: Tool;
  color: MarkColor;
  /** The brush's width, in the image's pixels. */
  brush: number;
};

/** What guides the next request on one image: its marks, and how much of its mask is painted. */
export type Guides = {
  marks: Mark[];
  /** For an animation, the frame the marks were drawn on, which is the frame they say something about. */
  frame: number | null;
  /** The number of the mark picked on the canvas. */
  selected: number | null;
  /** The share of the image the mask covers; 0 when nothing is painted. */
  painted: number;
};

const NO_GUIDES: Guides = {
  marks: [],
  frame: null,
  selected: null,
  painted: 0,
};
const listeners = new Set<() => void>();
let state: CanvasState = {
  tool: "circle",
  color: "red",
  brush: 64,
};
const guides = new Map<string, Guides>();
// What each image's guides were drawn on, so they are dropped once the image shows something else.
const drawnOn = new Map<string, string>();
// Kept apart from the viewport that shows them, so a mask outlives the image going out of view.
const masks = new Map<string, HTMLCanvasElement>();
// Counts up whenever a mask changes, so an upload of it is known to be current or not.
const revisions = new Map<string, number>();

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

function change(next: Partial<CanvasState>) {
  state = { ...state, ...next };
  emit();
}

export function useCanvas(): CanvasState {
  return useSyncExternalStore(subscribe, () => state);
}

/** Switch to a tool of the mode the canvas is in now, when the one picked is not. */
export function fitTool(mode: CanvasMode) {
  const keeps =
    state.tool === "pan" ||
    (mode === "mask"
      ? MASK_TOOLS.includes(state.tool)
      : !MASK_TOOLS.includes(state.tool));
  if (!keeps) {
    change({ tool: mode === "mask" ? "brush" : "circle" });
  }
}

export function setTool(tool: Tool) {
  change({ tool });
}

export function setColor(color: MarkColor) {
  change({ color });
}

export function setBrush(brush: number) {
  change({ brush });
}

function setGuides(name: string, next: Partial<Guides>) {
  guides.set(name, { ...(guides.get(name) ?? NO_GUIDES), ...next });
  emit();
}

/**
 * What guides the next request on the image named `name`, drawn on what it shows now, which `key` tells from anything
 * else it could show. Marks and a mask made on one version say nothing about another, so they go when it changes.
 */
export function useGuides(name: string, key: string | null): Guides {
  useEffect(() => {
    if (key === null) {
      return;
    }
    const before = drawnOn.get(name);
    drawnOn.set(name, key);
    if (before !== undefined && before !== key) {
      clearGuides(name);
    }
  }, [name, key]);
  return useSyncExternalStore(subscribe, () => guides.get(name) ?? NO_GUIDES);
}

export function guidesOf(name: string): Guides {
  return guides.get(name) ?? NO_GUIDES;
}

/**
 * Add a mark to the image's, and return its number. The first mark on an animation is drawn on `frame`, and those
 * after it join it there.
 */
export function addMark(
  name: string,
  mark: NewMark,
  frame: number | null = null,
): number {
  const { marks, frame: marked } = guidesOf(name);
  const id = marks.length + 1;
  setGuides(name, {
    marks: [...marks, { ...mark, id }],
    frame: marks.length === 0 ? frame : marked,
    selected: id,
  });
  return id;
}

export function updateMark(
  name: string,
  id: number,
  update: (mark: Mark) => Mark,
) {
  setGuides(name, {
    marks: guidesOf(name).marks.map((mark) =>
      mark.id === id ? update(mark) : mark,
    ),
  });
}

/** Remove a mark. Those after it move up a number, so the numbers stay the marks' places. */
export function removeMark(name: string, id: number) {
  const { marks, frame } = guidesOf(name);
  const left = marks
    .filter((mark) => mark.id !== id)
    .map((mark, index) => ({ ...mark, id: index + 1 }));
  setGuides(name, {
    marks: left,
    frame: left.length === 0 ? null : frame,
    selected: null,
  });
}

export function clearMarks(name: string) {
  setGuides(name, { marks: [], frame: null, selected: null });
}

export function selectMark(name: string, id: number | null) {
  if (guidesOf(name).selected !== id) {
    setGuides(name, { selected: id });
  }
}

/**
 * The canvas the image's mask is painted on, made for an image `width` by `height`. One made for another size is
 * replaced, since it would not fit.
 */
export function maskCanvas(
  name: string,
  width: number,
  height: number,
): HTMLCanvasElement {
  const scale = Math.min(1, MASK_EDGE / Math.max(width, height));
  const size = {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
  const kept = masks.get(name);
  if (kept && kept.width === size.width && kept.height === size.height) {
    return kept;
  }
  const canvas = document.createElement("canvas");
  canvas.width = size.width;
  canvas.height = size.height;
  masks.set(name, canvas);
  return canvas;
}

/** Paint or erase a stroke of the mask between two places on the image, with a brush `brush` of its pixels wide. */
export function paintMask(
  canvas: HTMLCanvasElement,
  from: [number, number],
  to: [number, number],
  brush: number,
  imageWidth: number,
  erase: boolean,
) {
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  context.globalCompositeOperation = erase ? "destination-out" : "source-over";
  context.strokeStyle = MASK_INK;
  context.lineWidth = (brush / imageWidth) * canvas.width;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.beginPath();
  context.moveTo(from[0] * canvas.width, from[1] * canvas.height);
  // A stroke of no length draws nothing, so a click moves a hair to leave a dot.
  context.lineTo(to[0] * canvas.width + 0.01, to[1] * canvas.height + 0.01);
  context.stroke();
}

/** Work out how much of the image's mask is painted, once a stroke has ended. */
export function measureMask(name: string) {
  const canvas = masks.get(name);
  const context = canvas?.getContext("2d");
  if (!canvas || !context) {
    return;
  }
  const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
  let filled = 0;
  for (let index = 3; index < data.length; index += 4 * SAMPLE) {
    if (data[index] > 0) {
      filled += 1;
    }
  }
  revisions.set(name, (revisions.get(name) ?? 0) + 1);
  setGuides(name, { painted: filled / (data.length / (4 * SAMPLE)) });
}

export function clearMask(name: string) {
  const canvas = masks.get(name);
  canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  revisions.set(name, (revisions.get(name) ?? 0) + 1);
  setGuides(name, { painted: 0 });
}

/** What tells the image's mask as it is now from the mask it was or will be. */
export function maskRevision(name: string): number {
  return revisions.get(name) ?? 0;
}

/**
 * The image's mask as a request sends it: a PNG `width` by `height`, transparent where the model may make changes
 * and opaque elsewhere, as a data URL. Null when nothing is painted.
 */
export function maskPng(
  name: string,
  width: number,
  height: number,
): string | null {
  const painted = masks.get(name);
  if (!painted || guidesOf(name).painted === 0) {
    return null;
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }
  context.fillStyle = "#000000";
  context.fillRect(0, 0, width, height);
  context.globalCompositeOperation = "destination-out";
  context.drawImage(painted, 0, 0, width, height);
  return canvas.toDataURL("image/png");
}

/** Drop the image's marks and mask, as once a request has taken them. */
export function clearGuides(name: string) {
  const canvas = masks.get(name);
  canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  revisions.set(name, (revisions.get(name) ?? 0) + 1);
  if (guides.has(name)) {
    guides.delete(name);
    emit();
  }
}

onRenamed((from, to) => {
  const after = (name: string) => movedPath(name, from, to);
  const moved = [
    rekey(guides, after),
    rekey(drawnOn, after),
    rekey(masks, after),
    rekey(revisions, after),
  ];
  if (moved.includes(true)) {
    emit();
  }
});
