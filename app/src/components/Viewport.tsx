import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent,
} from "react";

import { MarkLine, MarkList } from "@/components/Marks";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import { Tooltip } from "@/components/ui/tooltip";
import { ValueField } from "@/components/ui/value-field";
import type { ImageSummary, ImageVersion } from "@/lib/api";
import {
  addMark,
  BRUSH,
  clearMarks,
  clearMask,
  MARK_TOOLS,
  maskCanvas,
  measureMask,
  paintMask,
  removeMark,
  selectMark,
  setBrush,
  setColor,
  setTool,
  updateMark,
  useCanvas,
  useGuides,
  type CanvasMode,
} from "@/lib/canvas";
import { dimensions } from "@/lib/format";
import { pausePlayback, showFrame } from "@/lib/frames";
import {
  clampPoint,
  MARK_COLORS,
  markBox,
  moveMark,
  type Mark,
  type MarkColor,
  type MarkShape,
  type NewMark,
  type Point,
} from "@/lib/marks";
import {
  framePicture,
  usePicture,
  versionPicture,
  type Picture,
} from "@/lib/pictures";
import { useShortcuts } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import type { Shown } from "@/lib/viewed";

const RULER = 20;
// What a fitted image leaves free of the viewport, across and down: a share of it, so a small viewport gives the
// image more of its room, within these bounds. The least down still fits the label above the image, and the most
// keeps that label clear of the tools over the viewport's corner.
const FIT_ROOM = {
  x: { share: 0.1, min: 32, max: 96 },
  y: { share: 0.2, min: 60, max: 120 },
};
const LABEL = 22;
const LABEL_SHIFT = 8;
const ZOOM = { min: 0.1, max: 16, button: 1.25 };
// From here up a pixel is drawn as a square, so pixel art and single pixels can be read. A drawing has none.
const PIXELATED_FROM = 3;
// The pixels between ruler ticks, of which the first that leaves this much room on screen is used.
const TICK_STEPS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048];
const TICK_ROOM = 56;
// The frame an image being made shows in until the size it comes out at is known.
const UNKNOWN_SIZE = 1024;
// How much one notch of a wheel, and one pixel of a pinch, zooms.
const WHEEL = { notch: 0.0015, pinch: 0.01, line: 33 };
// A sketch is usually several strokes. Strokes keep joining the same mark until the pen has rested this long.
const SKETCH_PAUSE_MS = 1500;
// A press that barely moves makes a mark of a size of its own rather than one too small to see, as shares of the image.
const CLICKED = { least: 0.015, box: 0.16, arrow: 0.1, least_arrow: 0.02 };
const SMALLEST = 0.01;
// A stroke shorter than this is a slip of the hand, not the start of a sketch.
const SKETCH_POINTS = 3;
const CORNERS = ["tl", "tr", "bl", "br"] as const;

type Drag =
  | { kind: "pan"; x: number; y: number; from: View }
  | { kind: "draw"; start: Point; join: number | null }
  | { kind: "paint"; last: Point }
  | { kind: "move"; id: number; last: Point }
  | { kind: "resize"; id: number; fixed: Point };

/** The mark a drag from `start` to `to` draws. */
function drawn(
  shape: MarkShape,
  color: MarkColor,
  start: Point,
  to: Point,
): NewMark {
  if (shape === "arrow") {
    return { shape, color, tail: start, head: to };
  }
  if (shape === "sketch") {
    return { shape, color, strokes: [[start]] };
  }
  return {
    shape,
    color,
    x: Math.min(start[0], to[0]),
    y: Math.min(start[1], to[1]),
    w: Math.abs(to[0] - start[0]),
    h: Math.abs(to[1] - start[1]),
  };
}

/** A mark as it is kept once drawn: one from a press that barely moved gets a size it can be seen at. */
function finished(mark: NewMark, start: Point): NewMark {
  if (
    (mark.shape === "circle" || mark.shape === "box") &&
    (mark.w < CLICKED.least || mark.h < CLICKED.least)
  ) {
    const [x, y] = clampPoint([
      start[0] - CLICKED.box / 2,
      start[1] - CLICKED.box / 2,
    ]);
    return {
      ...mark,
      x: Math.min(x, 1 - CLICKED.box),
      y: Math.min(y, 1 - CLICKED.box),
      w: CLICKED.box,
      h: CLICKED.box,
    };
  }
  if (
    mark.shape === "arrow" &&
    Math.hypot(mark.head[0] - mark.tail[0], mark.head[1] - mark.tail[1]) <
      CLICKED.least_arrow
  ) {
    return {
      ...mark,
      tail: clampPoint([start[0] - CLICKED.arrow, start[1] + CLICKED.arrow]),
      head: start,
    };
  }
  return mark;
}

/** A ruler along the top or left edge, in the image's pixels, with a tick at each of its edges. */
function Ruler({
  horizontal,
  origin,
  zoom,
  length,
  extent,
}: {
  horizontal: boolean;
  /** Where the image's edge is in the viewport. */
  origin: number;
  zoom: number;
  /** How long the viewport is along it. */
  length: number;
  /** How long the image is along it, in its pixels. */
  extent: number;
}) {
  const step =
    TICK_STEPS.find((candidate) => candidate * zoom >= TICK_ROOM) ?? 4096;
  const ticks: { at: number; value: number }[] = [];
  const first = Math.ceil((RULER - origin) / (step * zoom));
  for (let index = first; origin + index * step * zoom < length; index += 1) {
    ticks.push({
      at: origin - RULER + index * step * zoom,
      value: index * step,
    });
  }
  const tick = horizontal
    ? "top-0 bottom-0 border-l pt-[3px] pl-1"
    : "right-0 left-0 border-t pt-1 pl-[3px]";
  const place = (at: number) => (horizontal ? { left: at } : { top: at });
  return (
    <div
      aria-hidden
      className={cn(
        "absolute z-20 overflow-hidden bg-panel font-mono text-[10px]/3 font-medium text-ink-muted tabular-nums",
        horizontal
          ? "top-0 right-0 left-5 h-5 border-b border-line"
          : "top-5 bottom-0 left-0 w-5 border-r border-line",
      )}
    >
      {ticks.map(({ at, value }) => (
        <span
          key={value}
          style={place(at)}
          className={cn(
            "absolute",
            tick,
            value === 0 || value === extent
              ? "border-ink-muted text-ink"
              : "border-line-control",
          )}
        >
          <span
            className={cn(
              !horizontal && "block rotate-180 [writing-mode:vertical-rl]",
            )}
          >
            {value}
          </span>
        </span>
      ))}
      <span
        style={place(origin - RULER + extent * zoom)}
        className={cn("absolute border-ink-muted", tick)}
      />
    </div>
  );
}

type View = { zoom: number | null; x: number; y: number };

const FITTED: View = { zoom: null, x: 0, y: 0 };

/**
 * The image in view between its rulers, over the checkerboard where it is transparent. It starts fitted; a wheel
 * zooms on the pointer and a drag moves it. Compare shows the version before in its place. While a run works on
 * the image, what the image's file holds gives way to the run's latest in-progress image. In a mode, the marks or
 * the mask that guide the next request are drawn over it with the tool picked. An animation shows one frame at a
 * time, and its marks only on the frame they were drawn on.
 */
export function Viewport({
  image,
  shown,
  before,
  live,
  mode,
  animation,
}: {
  image: ImageSummary;
  shown: Shown;
  before: ImageVersion | null;
  /**
   * While a run works on the image: its latest in-progress image, the size it was asked for, if any, and whether marks
   * can be drawn over it to steer the run.
   */
  live: {
    preview: Picture | null;
    size: [number, number] | null;
    steering: boolean;
  } | null;
  /** What is drawn over the image to guide a request; null when it can take neither marks nor a mask. */
  mode: CanvasMode | null;
  /**
   * For an animation: the frame that shows, whether it plays, and the frame the marks for the next request are on,
   * if it has any.
   */
  animation: { frame: number; playing: boolean; marked: number | null } | null;
}) {
  const [box, setBox] = useState({ width: 0, height: 0 });
  const [view, setView] = useState(FITTED);
  // A new image is fitted once its first file comes, whatever was done to the view while it was made.
  const [hadFile, setHadFile] = useState(shown.width !== null);
  if ((shown.width !== null) !== hadFile) {
    setHadFile(shown.width !== null);
    if (shown.width !== null) {
      setView(FITTED);
    }
  }
  const [compare, setCompare] = useState(false);
  const [panning, setPanning] = useState(false);
  const [draft, setDraft] = useState<NewMark | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const drag = useRef<Drag | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  // The sketch still taking strokes: its number, and how many marks there were when it was made.
  const sketch = useRef<{ id: number; count: number; color: MarkColor } | null>(
    null,
  );
  const pause = useRef<number | undefined>(undefined);
  const { tool, color, brush } = useCanvas();
  const guides = useGuides(image.name, shown.picture?.key ?? null);

  const compared = compare ? before : null;
  // What the run makes lands in the image's file, so it forms where that shows, and not over another version.
  const forming = live !== null && shown.file && compared === null;
  const preview = forming ? live.preview : null;
  // Of an animation, the frame in turn. The version before shows its own frame at that place, or its last.
  const frameOf = (of: Picture, frames: number) =>
    animation && frames > 1
      ? framePicture(of, Math.min(animation.frame, frames - 1))
      : of;
  const picture = compared
    ? frameOf(versionPicture(image, compared), compared.frames)
    : (preview ?? (shown.picture && frameOf(shown.picture, shown.frames)));
  // The marks sit on one frame of an animation, so they show and are drawn only there, and not while it plays.
  const elsewhere =
    animation !== null &&
    animation.marked !== null &&
    (animation.playing || animation.frame !== animation.marked)
      ? animation.marked
      : null;
  // An image with no file yet takes the size the run was asked for.
  const blank = forming && shown.width === null;
  const width =
    (compared ?? shown).width ?? (blank ? (live.size?.[0] ?? UNKNOWN_SIZE) : 0);
  const height =
    (compared ?? shown).height ??
    (blank ? (live.size?.[1] ?? UNKNOWN_SIZE) : 0);
  const id = compared ? compared.id : (shown.version?.id ?? null);
  const { url, error } = usePicture(picture);
  const vector = image.name.toLowerCase().endsWith(".svg");
  // Marks and the mask are drawn on what the next request edits, so not on the version before or an image forming,
  // except the marks of a message to the agent drawing it, which go on its latest render.
  const guiding =
    mode !== null &&
    url !== null &&
    compared === null &&
    elsewhere === null &&
    (live === null || live.steering)
      ? mode
      : null;
  const marks = guiding === "markup" ? guides.marks : [];
  const selected = marks.find((mark) => mark.id === guides.selected) ?? null;
  const selectedBox = selected ? markBox(selected) : null;
  const active =
    guiding === "markup"
      ? tool === "brush" || tool === "eraser"
        ? "select"
        : tool
      : guiding === "mask"
        ? tool === "brush" || tool === "eraser"
          ? tool
          : "pan"
        : "pan";
  const drawing = (MARK_TOOLS as readonly string[]).includes(active);
  const painting = active === "brush" || active === "eraser";

  const closeSketch = () => {
    window.clearTimeout(pause.current);
    sketch.current = null;
  };
  // Another tool, color, or mode ends the sketch that was taking strokes.
  useEffect(
    () => () => {
      window.clearTimeout(pause.current);
      sketch.current = null;
    },
    [tool, color, mode],
  );

  const fit =
    width > 0 && height > 0 && box.width > 0
      ? Math.min(
          ZOOM.max,
          Math.max(
            0.01,
            Math.min(
              (box.width - RULER - room(box.width, FIT_ROOM.x)) / width,
              (box.height - RULER - room(box.height, FIT_ROOM.y)) / height,
            ),
          ),
        )
      : 1;
  const zoom = view.zoom ?? fit;
  const left = Math.round(
    RULER + (box.width - RULER - width * zoom) / 2 + view.x,
  );
  const top = Math.round(
    RULER + (box.height - RULER - height * zoom) / 2 + LABEL_SHIFT + view.y,
  );

  // What the wheel listener reads, which is attached once and so cannot see a render's own values.
  const geometry = useRef({ zoom, left, top, box, width, height, fit });
  useEffect(() => {
    geometry.current = { zoom, left, top, box, width, height, fit };
  });

  const hostElement = useRef<HTMLDivElement | null>(null);
  const host = useCallback((element: HTMLDivElement | null) => {
    hostElement.current = element;
    if (!element) {
      return;
    }
    const observer = new ResizeObserver(([entry]) =>
      setBox({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      }),
    );
    observer.observe(element);
    // Not React's onWheel, which is passive: a pinch would also zoom the page.
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const now = geometry.current;
      if (now.width === 0) {
        return;
      }
      const rect = element.getBoundingClientRect();
      const at = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const delta =
        event.deltaMode === WheelEvent.DOM_DELTA_LINE
          ? event.deltaY * WHEEL.line
          : event.deltaY;
      const next = clamped(
        now.zoom *
          Math.exp(-delta * (event.ctrlKey ? WHEEL.pinch : WHEEL.notch)),
        now.fit,
      );
      // The pixel under the pointer stays under it.
      const pixel = {
        x: (at.x - now.left) / now.zoom,
        y: (at.y - now.top) / now.zoom,
      };
      setView({
        zoom: next,
        x:
          at.x -
          pixel.x * next -
          RULER -
          (now.box.width - RULER - now.width * next) / 2,
        y:
          at.y -
          pixel.y * next -
          RULER -
          (now.box.height - RULER - now.height * next) / 2 -
          LABEL_SHIFT,
      });
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      observer.disconnect();
      element.removeEventListener("wheel", onWheel);
    };
  }, []);

  const zoomBy = (factor: number) =>
    setView((current) => ({
      ...current,
      zoom: clamped((current.zoom ?? fit) * factor, fit),
    }));
  const fitIt = () => setView(FITTED);
  const toggleCompare = () => before && setCompare((on) => !on);
  const deleteSelected = () => selected && removeMark(image.name, selected.id);

  useShortcuts({
    f: fitIt,
    c: toggleCompare,
    "+": () => zoomBy(ZOOM.button),
    "=": () => zoomBy(ZOOM.button),
    "-": () => zoomBy(1 / ZOOM.button),
    delete: deleteSelected,
    backspace: deleteSelected,
    escape: () => selectMark(image.name, null),
  });

  /** Where on the image the pointer is, as shares of its width and height, which are outside 0 to 1 beside it. */
  const pointOf = (event: { clientX: number; clientY: number }): Point => {
    const rect = stage.current?.getBoundingClientRect();
    return rect && rect.width > 0
      ? [
          (event.clientX - rect.left) / rect.width,
          (event.clientY - rect.top) / rect.height,
        ]
      : [-1, -1];
  };

  const hold = (event: PointerEvent<Element>) => {
    // Capture can be refused when the pointer is already gone; the drag then simply ends where it is.
    try {
      hostElement.current?.setPointerCapture(event.pointerId);
    } catch {
      // Nothing to hold on to.
    }
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 && event.button !== 1) {
      return;
    }
    hold(event);
    const point = pointOf(event);
    const inside =
      point[0] >= 0 && point[0] <= 1 && point[1] >= 0 && point[1] <= 1;
    if (event.button === 0 && inside && drawing) {
      // A mark belongs to the frame it is drawn on, so the animation holds on that frame.
      if (animation?.playing) {
        pausePlayback(image.name);
      }
      window.clearTimeout(pause.current);
      const open = sketch.current;
      const joins =
        active === "sketch" &&
        open !== null &&
        open.color === color &&
        guides.marks.length === open.count &&
        guides.marks.some(
          (mark) => mark.id === open.id && mark.shape === "sketch",
        );
      drag.current = {
        kind: "draw",
        start: point,
        join: joins && open ? open.id : null,
      };
      setDraft(drawn(active as MarkShape, color, point, point));
      return;
    }
    if (event.button === 0 && inside && painting) {
      drag.current = { kind: "paint", last: point };
      paintMask(
        maskCanvas(image.name, width, height),
        point,
        point,
        brush,
        width,
        active === "eraser",
      );
      return;
    }
    if (guiding === "markup") {
      selectMark(image.name, null);
    }
    drag.current = {
      kind: "pan",
      x: event.clientX,
      y: event.clientY,
      from: view,
    };
    setPanning(true);
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (painting) {
      const rect = event.currentTarget.getBoundingClientRect();
      setCursor({ x: event.clientX - rect.left, y: event.clientY - rect.top });
    }
    const current = drag.current;
    if (!current) {
      return;
    }
    if (current.kind === "pan") {
      setView({
        ...current.from,
        x: current.from.x + event.clientX - current.x,
        y: current.from.y + event.clientY - current.y,
      });
      return;
    }
    const point = pointOf(event);
    const held = clampPoint(point);
    if (current.kind === "draw") {
      setDraft((mark) =>
        mark === null
          ? null
          : mark.shape === "sketch"
            ? { ...mark, strokes: [[...mark.strokes[0], held]] }
            : drawn(mark.shape, mark.color, current.start, held),
      );
    } else if (current.kind === "paint") {
      paintMask(
        maskCanvas(image.name, width, height),
        current.last,
        point,
        brush,
        width,
        active === "eraser",
      );
      current.last = point;
    } else if (current.kind === "move") {
      const [dx, dy] = [point[0] - current.last[0], point[1] - current.last[1]];
      current.last = point;
      updateMark(image.name, current.id, (mark) => moveMark(mark, dx, dy));
    } else {
      const [fx, fy] = current.fixed;
      updateMark(image.name, current.id, (mark) =>
        mark.shape === "circle" || mark.shape === "box"
          ? {
              ...mark,
              x: Math.min(fx, held[0]),
              y: Math.min(fy, held[1]),
              w: Math.max(SMALLEST, Math.abs(held[0] - fx)),
              h: Math.max(SMALLEST, Math.abs(held[1] - fy)),
            }
          : mark,
      );
    }
  };

  const endDrag = () => {
    const current = drag.current;
    drag.current = null;
    setPanning(false);
    if (current?.kind === "paint") {
      measureMask(image.name);
    }
    if (current?.kind !== "draw" || draft === null) {
      return;
    }
    setDraft(null);
    const mark = finished(draft, current.start);
    const frame = animation?.frame ?? null;
    if (mark.shape !== "sketch") {
      addMark(image.name, mark, frame);
      return;
    }
    if (current.join !== null) {
      const stroke = mark.strokes[0];
      updateMark(image.name, current.join, (joined) =>
        joined.shape === "sketch"
          ? { ...joined, strokes: [...joined.strokes, stroke] }
          : joined,
      );
    } else if (mark.strokes[0].length > SKETCH_POINTS) {
      const id = addMark(image.name, mark, frame);
      sketch.current = { id, count: id, color: mark.color };
    }
    pause.current = window.setTimeout(closeSketch, SKETCH_PAUSE_MS);
  };

  const startMove = (mark: Mark) => (event: PointerEvent<SVGPathElement>) => {
    if (event.button !== 0) {
      return;
    }
    event.stopPropagation();
    hold(event);
    drag.current = { kind: "move", id: mark.id, last: pointOf(event) };
    selectMark(image.name, mark.id);
  };

  const startResize =
    (corner: (typeof CORNERS)[number]) =>
    (event: PointerEvent<HTMLSpanElement>) => {
      if (!selected || !selectedBox) {
        return;
      }
      event.stopPropagation();
      hold(event);
      // The corner across from the one held stays where it is.
      const fixed: Point = [
        corner.includes("l") ? selectedBox.x + selectedBox.w : selectedBox.x,
        corner.includes("t") ? selectedBox.y + selectedBox.h : selectedBox.y,
      ];
      drag.current = { kind: "resize", id: selected.id, fixed };
    };

  /** Pick a mark from the list, and bring it into view when the canvas is zoomed past it. */
  const showMark = (mark: Mark) => {
    const area = markBox(mark);
    const x = left + (area.x + area.w / 2) * width * zoom;
    const y = top + (area.y + area.h / 2) * height * zoom;
    const seen =
      x > RULER + 24 &&
      x < box.width - 24 &&
      y > RULER + 24 &&
      y < box.height - 24;
    selectMark(image.name, mark.id);
    setTool("select");
    if (!seen) {
      setView((current) => ({
        ...current,
        x: current.x + (RULER + box.width) / 2 - x,
        y: current.y + (RULER + box.height) / 2 - y,
      }));
    }
  };

  const maskHost = useCallback(
    (element: HTMLDivElement | null) => {
      if (!element) {
        return;
      }
      const canvas = maskCanvas(image.name, width, height);
      canvas.className = "block size-full";
      element.appendChild(canvas);
      return () => canvas.remove();
    },
    [image.name, width, height],
  );

  // A name whose only runs made nothing is not a failure of its own: how the last run ended is said elsewhere.
  const unmade =
    picture === null &&
    live === null &&
    image.versions.length === 0 &&
    (image.last_run !== null || (image.design ?? null) !== null);
  const missing =
    picture !== null || live !== null || unmade
      ? null
      : image.versions.length > 0
        ? "This image's file is gone or can't be read. Pick a version below and restore it."
        : "This file is not an image the app can show.";

  return (
    <div
      ref={host}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onPointerLeave={() => setCursor(null)}
      // A press of the wheel would otherwise start the browser's own scrolling.
      onMouseDown={(event) => event.button === 1 && event.preventDefault()}
      className={cn(
        "relative min-h-0 min-w-0 flex-1 touch-none overflow-hidden bg-canvas select-none",
        width > 0 &&
          (panning
            ? "cursor-grabbing"
            : active === "pan"
              ? "cursor-grab"
              : "cursor-default"),
      )}
    >
      <div
        aria-hidden
        className="absolute top-0 left-0 z-30 size-5 border-r border-b border-line bg-panel"
      />
      {live && (
        <div
          role="progressbar"
          aria-label="Working"
          className="absolute top-5 right-0 left-5 z-20 h-0.5 overflow-hidden"
        >
          <span className="absolute inset-y-0 w-[32%] animate-slide bg-accent" />
        </div>
      )}
      <Ruler
        horizontal
        origin={left}
        zoom={zoom}
        length={box.width}
        extent={width}
      />
      <Ruler
        horizontal={false}
        origin={top}
        zoom={zoom}
        length={box.height}
        extent={height}
      />
      {width > 0 && (
        <>
          <div
            style={{
              left,
              top: top - LABEL,
              width: Math.max(width * zoom, 220),
            }}
            className="pointer-events-none absolute flex items-baseline gap-2 whitespace-nowrap text-ink-muted"
          >
            <span className="text-caption font-medium text-ink">
              {image.name}
            </span>
            <span className="mono-annotation">
              {id && `${id}  `}
              {dimensions(width, height)}
            </span>
            {compared && (
              <span className="bg-accent px-1.5 mono-annotation text-on-accent">
                before, {compared.id}
              </span>
            )}
            {preview && (
              <span className="bg-accent px-1.5 mono-annotation text-on-accent">
                in progress
              </span>
            )}
          </div>
          <div
            ref={stage}
            style={{ left, top, width: width * zoom, height: height * zoom }}
            className={cn(
              "absolute grid place-items-center outline outline-line",
              url ? "checker" : "bg-panel",
              drawing && "cursor-crosshair",
              painting && "cursor-none",
            )}
          >
            {url ? (
              <img
                src={url}
                alt={id ? `${image.name} ${id}` : image.name}
                draggable={false}
                className={cn(
                  "pointer-events-none absolute inset-0 block size-full",
                  // An in-progress image can come at another size than the image it will replace.
                  preview && "object-contain",
                  zoom >= PIXELATED_FROM &&
                    !vector &&
                    "[image-rendering:pixelated]",
                )}
              />
            ) : (
              !error && (
                <span className="flex flex-col items-center gap-2 text-title">
                  <LoadingMark size={24} />
                  {blank && "Generating your image"}
                </span>
              )
            )}
            {guiding === "mask" && (
              <div
                ref={maskHost}
                className="pointer-events-none absolute inset-0 opacity-55"
              />
            )}
            {guiding === "markup" && (
              <svg
                width={width * zoom}
                height={height * zoom}
                className="pointer-events-none absolute inset-0 overflow-visible"
              >
                {marks.map((mark) => (
                  <MarkLine
                    key={mark.id}
                    mark={mark}
                    width={width * zoom}
                    height={height * zoom}
                    onPress={active === "select" ? startMove(mark) : undefined}
                  />
                ))}
                {draft && (
                  <MarkLine
                    mark={draft}
                    width={width * zoom}
                    height={height * zoom}
                  />
                )}
              </svg>
            )}
            {selected && selectedBox && (
              <div
                style={{
                  left: selectedBox.x * width * zoom - 1,
                  top: selectedBox.y * height * zoom - 1,
                  width: selectedBox.w * width * zoom + 2,
                  height: selectedBox.h * height * zoom + 2,
                }}
                className="pointer-events-none absolute z-10 border border-accent-ink"
              >
                {(selected.shape === "circle" || selected.shape === "box") &&
                  CORNERS.map((corner) => (
                    <span
                      key={corner}
                      onPointerDown={startResize(corner)}
                      className={cn(
                        "pointer-events-auto absolute size-1.75 border border-accent-ink bg-panel",
                        corner.includes("t") ? "-top-1" : "-bottom-1",
                        corner.includes("l") ? "-left-1" : "-right-1",
                        corner === "tl" || corner === "br"
                          ? "cursor-nwse-resize"
                          : "cursor-nesw-resize",
                      )}
                    />
                  ))}
                {selectedBox.w > 0.02 && (
                  <span className="absolute -bottom-5.5 left-1/2 -translate-x-1/2 bg-accent px-1.5 py-px mono-annotation whitespace-nowrap text-on-accent">
                    {dimensions(
                      Math.round(selectedBox.w * width),
                      Math.round(selectedBox.h * height),
                    )}
                  </span>
                )}
              </div>
            )}
          </div>
        </>
      )}
      {(missing ?? error) && (
        <Notice className="absolute top-8 right-3 left-8 z-10 mr-44 cursor-default">
          {missing ?? `Could not read the image. ${error}`}
        </Notice>
      )}
      {unmade && (
        <Notice
          tone="neutral"
          icon="image"
          className="absolute top-8 right-3 left-8 z-10 mr-44 cursor-default"
        >
          No image has been made for this name yet. Generate again, or delete
          it.
        </Notice>
      )}
      {painting && cursor && (
        <span
          aria-hidden
          style={{
            left: cursor.x,
            top: cursor.y,
            width: brush * zoom,
            height: brush * zoom,
          }}
          className="ring-white/70 pointer-events-none absolute z-20 -translate-1/2 rounded-full border border-ink ring-1"
        />
      )}
      {guiding === "markup" && (
        <div
          onPointerDown={(event) => event.stopPropagation()}
          className="absolute top-8 left-8 z-30 flex min-h-8 cursor-default items-center gap-2 rounded-md border border-line bg-panel px-2 py-0.75"
        >
          <span className="text-label text-ink-muted">
            {selected ? `Mark ${selected.id}` : "Mark color"}
          </span>
          {MARK_COLORS.map((each) => (
            <Tooltip key={each.id} content={each.id}>
              <button
                type="button"
                aria-label={each.id}
                aria-pressed={(selected?.color ?? color) === each.id}
                style={{ background: each.hex }}
                onClick={() => {
                  setColor(each.id);
                  if (selected) {
                    updateMark(image.name, selected.id, (mark) => ({
                      ...mark,
                      color: each.id,
                    }));
                  }
                }}
                className="size-3.5 shrink-0 rounded-sm border border-line-control aria-pressed:outline-2 aria-pressed:outline-offset-1 aria-pressed:outline-ink"
              />
            </Tooltip>
          ))}
          {selected && (
            <Tooltip content="Delete mark" keys="Del">
              <Button
                size="sm"
                icon
                aria-label="Delete mark"
                onClick={deleteSelected}
              >
                <Icon name="delete" />
              </Button>
            </Tooltip>
          )}
          {!selected && marks.length > 1 && (
            <Button size="sm" onClick={() => clearMarks(image.name)}>
              Clear all
            </Button>
          )}
        </div>
      )}
      {elsewhere !== null && (
        <div
          onPointerDown={(event) => event.stopPropagation()}
          className="absolute top-8 left-8 z-30 flex min-h-8 cursor-default items-center gap-2 rounded-md border border-line bg-panel px-2 py-0.75"
        >
          <span className="text-label text-ink-muted">
            Marks are on frame {elsewhere + 1}
          </span>
          <Button size="sm" onClick={() => showFrame(image.name, elsewhere)}>
            Go to frame
          </Button>
        </div>
      )}
      {guiding === "mask" && (
        <div
          onPointerDown={(event) => event.stopPropagation()}
          className="absolute top-8 left-8 z-30 flex min-h-8 cursor-default items-center gap-2 rounded-md border border-line bg-panel px-2 py-0.75"
        >
          <ValueField
            label="Brush"
            className="w-37"
            value={brush}
            min={BRUSH.min}
            max={BRUSH.max}
            step={BRUSH.step}
            unit="px"
            onChange={setBrush}
          />
          <Button
            size="sm"
            disabled={guides.painted === 0}
            onClick={() => clearMask(image.name)}
          >
            Clear mask
          </Button>
        </div>
      )}
      {guiding === "markup" && url && marks.length > 0 && (
        <MarkList
          marks={marks}
          selected={guides.selected}
          url={url}
          width={width}
          height={height}
          onShow={showMark}
          onDelete={(mark) => removeMark(image.name, mark.id)}
        />
      )}
      <div
        onPointerDown={(event) => event.stopPropagation()}
        className="absolute top-8 right-3 z-30 flex cursor-default items-center gap-1 rounded-md border border-line bg-panel p-0.75"
      >
        <Tooltip content="Zoom out" keys="-">
          <Button
            size="sm"
            icon
            aria-label="Zoom out"
            onClick={() => zoomBy(1 / ZOOM.button)}
          >
            <Icon name="minus" />
          </Button>
        </Tooltip>
        <span className="min-w-10 text-center mono-value">
          {Math.round(zoom * 100)}%
        </span>
        <Tooltip content="Zoom in" keys="+">
          <Button
            size="sm"
            icon
            aria-label="Zoom in"
            onClick={() => zoomBy(ZOOM.button)}
          >
            <Icon name="add" />
          </Button>
        </Tooltip>
        <Tooltip content="Fit" keys="F">
          <Button size="sm" icon aria-label="Fit" onClick={fitIt}>
            <Icon name="fit" />
          </Button>
        </Tooltip>
        <span aria-hidden className="mx-0.5 h-4 w-px bg-line" />
        <Tooltip
          content={before ? `Compare with ${before.id}` : "Compare"}
          keys="C"
        >
          <Button
            size="sm"
            icon
            aria-label="Compare with the version before"
            aria-pressed={compared !== null}
            disabled={before === null}
            onClick={toggleCompare}
          >
            <Icon name="compare" />
          </Button>
        </Tooltip>
      </div>
    </div>
  );
}

function room(
  length: number,
  { share, min, max }: { share: number; min: number; max: number },
): number {
  return Math.min(max, Math.max(min, length * share));
}

function clamped(zoom: number, fit: number): number {
  return Math.min(ZOOM.max, Math.max(Math.min(ZOOM.min, fit), zoom));
}
