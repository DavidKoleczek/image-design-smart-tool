import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import { Tooltip } from "@/components/ui/tooltip";
import type { ImageSummary, ImageVersion } from "@/lib/api";
import { dimensions } from "@/lib/format";
import { usePicture, versionPicture } from "@/lib/pictures";
import { useShortcuts } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import type { Shown } from "@/lib/viewed";

const RULER = 20;
// What a fitted image leaves free of the viewport, across and down: a share of it, so a small viewport gives the
// image more of its room, within these bounds. The least down still fits the label above the image.
const FIT_ROOM = {
  x: { share: 0.1, min: 32, max: 96 },
  y: { share: 0.16, min: 60, max: 112 },
};
const LABEL = 22;
const LABEL_SHIFT = 8;
const ZOOM = { min: 0.1, max: 16, button: 1.25 };
// From here up a pixel is drawn as a square, so pixel art and single pixels can be read. A drawing has none.
const PIXELATED_FROM = 3;
// The pixels between ruler ticks, of which the first that leaves this much room on screen is used.
const TICK_STEPS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048];
const TICK_ROOM = 56;
// How much one notch of a wheel, and one pixel of a pinch, zooms.
const WHEEL = { notch: 0.0015, pinch: 0.01, line: 33 };

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
 * zooms on the pointer and a drag moves it. Compare shows the version before in its place.
 */
export function Viewport({
  image,
  shown,
  before,
}: {
  image: ImageSummary;
  shown: Shown;
  before: ImageVersion | null;
}) {
  const [box, setBox] = useState({ width: 0, height: 0 });
  const [view, setView] = useState(FITTED);
  const [compare, setCompare] = useState(false);
  const [panning, setPanning] = useState(false);
  const drag = useRef<{ x: number; y: number; from: View } | null>(null);

  const compared = compare ? before : null;
  const picture = compared ? versionPicture(image, compared) : shown.picture;
  const width = (compared ?? shown).width ?? 0;
  const height = (compared ?? shown).height ?? 0;
  const id = compared ? compared.id : (shown.version?.id ?? null);
  const { url, error } = usePicture(picture);
  const vector = image.name.toLowerCase().endsWith(".svg");

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

  const host = useCallback((element: HTMLDivElement | null) => {
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

  useShortcuts({
    f: fitIt,
    c: toggleCompare,
    "+": () => zoomBy(ZOOM.button),
    "=": () => zoomBy(ZOOM.button),
    "-": () => zoomBy(1 / ZOOM.button),
  });

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 && event.button !== 1) {
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, from: view };
    setPanning(true);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const from = drag.current;
    if (from) {
      setView({
        ...from.from,
        x: from.from.x + event.clientX - from.x,
        y: from.from.y + event.clientY - from.y,
      });
    }
  };
  const endDrag = () => {
    drag.current = null;
    setPanning(false);
  };

  const missing =
    picture === null
      ? image.versions.length > 0
        ? "This image's file is gone or can't be read. Pick a version below and restore it."
        : "This file is not an image the app can show."
      : null;

  return (
    <div
      ref={host}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      // A press of the wheel would otherwise start the browser's own scrolling.
      onMouseDown={(event) => event.button === 1 && event.preventDefault()}
      className={cn(
        "relative min-h-0 flex-1 touch-none overflow-hidden bg-canvas select-none",
        width > 0 && (panning ? "cursor-grabbing" : "cursor-grab"),
      )}
    >
      <div
        aria-hidden
        className="absolute top-0 left-0 z-30 size-5 border-r border-b border-line bg-panel"
      />
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
          </div>
          <div
            style={{ left, top, width: width * zoom, height: height * zoom }}
            className={cn(
              "absolute grid place-items-center outline outline-line",
              url ? "checker" : "bg-panel",
            )}
          >
            {url ? (
              <img
                src={url}
                alt={id ? `${image.name} ${id}` : image.name}
                draggable={false}
                className={cn(
                  "pointer-events-none absolute inset-0 block size-full",
                  zoom >= PIXELATED_FROM &&
                    !vector &&
                    "[image-rendering:pixelated]",
                )}
              />
            ) : (
              !error && <LoadingMark size={24} />
            )}
          </div>
        </>
      )}
      {(missing ?? error) && (
        <Notice className="absolute top-8 right-3 left-8 z-10 mr-44 cursor-default">
          {missing ?? `Could not read the image. ${error}`}
        </Notice>
      )}
      <div
        onPointerDown={(event) => event.stopPropagation()}
        className="absolute top-8 right-3 z-30 flex cursor-default items-center gap-1 rounded-md border border-line bg-panel p-[3px]"
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
