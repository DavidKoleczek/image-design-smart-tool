import type { PointerEvent } from "react";

import { Icon } from "@/components/ui/icon";
import { Tooltip } from "@/components/ui/tooltip";
import {
  markBox,
  markColor,
  markName,
  markPath,
  type Mark,
  type MarkColor,
  type Shape,
} from "@/lib/marks";
import { cn } from "@/lib/utils";

const TILE = { width: 64, height: 48 };
// A mark's line on the canvas, the white under it that keeps it readable on any image, and how near counts as on it.
const LINE = { width: 3, halo: 6, reach: 18 };

/** A mark drawn over the image, in an SVG `width` by `height`. With `onPress`, it can be picked up. */
export function MarkLine({
  mark,
  width,
  height,
  onPress,
}: {
  mark: Shape & { color: MarkColor };
  width: number;
  height: number;
  onPress?: (event: PointerEvent<SVGPathElement>) => void;
}) {
  const round = mark.shape === "sketch";
  const closed = mark.shape === "circle" || mark.shape === "box";
  const line = {
    d: markPath(mark, width, height),
    fill: "none",
    strokeLinecap: round ? ("round" as const) : ("square" as const),
    strokeLinejoin: round ? ("round" as const) : ("miter" as const),
  };
  return (
    <g>
      <path {...line} stroke="#ffffff" strokeWidth={LINE.halo} opacity={0.9} />
      <path
        {...line}
        stroke={markColor(mark.color).hex}
        strokeWidth={LINE.width}
      />
      {onPress && (
        <path
          {...line}
          stroke="transparent"
          strokeWidth={LINE.reach}
          fill={closed ? "transparent" : "none"}
          className="pointer-events-auto cursor-move"
          onPointerDown={onPress}
        />
      )}
    </g>
  );
}

/** The marks alone, as a request sends them beside the image, or drawn over `url` as on its marked copy. */
export function MarksPicture({
  marks,
  width,
  height,
  url,
  className,
}: {
  marks: Mark[];
  width: number;
  height: number;
  url?: string | null;
  className?: string;
}) {
  // Drawn at a size where the lines read, whatever the size it is shown at.
  const scale = 320 / Math.max(width, height);
  const size = { width: width * scale, height: height * scale };
  return (
    <svg
      viewBox={`0 0 ${size.width} ${size.height}`}
      aria-hidden
      className={className}
    >
      {url && <image href={url} {...size} />}
      {marks.map((mark) => (
        <MarkLine key={mark.id} mark={mark} {...size} />
      ))}
    </svg>
  );
}

/** The part of the image a mark's tile shows: the mark with room around it, at the tile's shape, inside the image. */
function tileCrop(mark: Mark, width: number, height: number) {
  const box = markBox(mark);
  const ratio = TILE.width / TILE.height;
  let across = Math.max(box.w * width, box.h * height * ratio) * 1.5;
  across = Math.min(width, Math.max(across, width * 0.22));
  let down = across / ratio;
  if (down > height) {
    down = height;
    across = down * ratio;
  }
  return {
    x: Math.min(
      width - across,
      Math.max(0, (box.x + box.w / 2) * width - across / 2),
    ),
    y: Math.min(
      height - down,
      Math.max(0, (box.y + box.h / 2) * height - down / 2),
    ),
    width: across,
    height: down,
  };
}

/** The marks down the side of the canvas, in the order they were made: click one to show it, or delete it. */
export function MarkList({
  marks,
  selected,
  url,
  width,
  height,
  onShow,
  onDelete,
}: {
  marks: Mark[];
  selected: number | null;
  /** The image the marks are on. */
  url: string;
  width: number;
  height: number;
  onShow: (mark: Mark) => void;
  onDelete: (mark: Mark) => void;
}) {
  return (
    <ol
      aria-label="Marks"
      onPointerDown={(event) => event.stopPropagation()}
      className="absolute top-18 left-8 z-30 flex max-h-[calc(100%-96px)] cursor-default flex-col gap-1.5 overflow-y-auto rounded-md border border-line bg-panel p-1"
    >
      {marks.map((mark) => {
        const crop = tileCrop(mark, width, height);
        const color = markColor(mark.color);
        const current = selected === mark.id;
        const line = {
          d: markPath(mark, width, height, crop.width * 0.14),
          fill: "none",
          vectorEffect: "non-scaling-stroke" as const,
          strokeLinecap: "round" as const,
          strokeLinejoin: "round" as const,
        };
        return (
          <li key={mark.id} className="group relative shrink-0">
            <Tooltip content={markName(mark)} side="right">
              <button
                type="button"
                aria-label={markName(mark)}
                aria-current={current || undefined}
                onClick={() => onShow(mark)}
                className={cn(
                  "relative block h-12 w-16 overflow-hidden rounded-sm border bg-canvas focus-visible:focus-ring focus-visible:outline-none",
                  current
                    ? "border-accent-ink ring-1 ring-accent-ink"
                    : "border-line hover:border-line-control",
                )}
              >
                <svg
                  viewBox={`${crop.x} ${crop.y} ${crop.width} ${crop.height}`}
                  preserveAspectRatio="xMidYMid slice"
                  aria-hidden
                  className="block size-full"
                >
                  <image href={url} width={width} height={height} />
                  <path
                    {...line}
                    stroke="#ffffff"
                    strokeWidth={3.5}
                    opacity={0.9}
                  />
                  <path {...line} stroke={color.hex} strokeWidth={2} />
                </svg>
                <span
                  style={{ background: color.hex, color: color.on }}
                  className="absolute bottom-0.5 left-0.5 grid h-4 min-w-4 place-items-center rounded-[2px] px-0.75 mono-annotation font-semibold"
                >
                  {mark.id}
                </span>
              </button>
            </Tooltip>
            <Tooltip content="Delete this mark" side="right">
              <button
                type="button"
                aria-label={`Delete mark ${mark.id}`}
                onClick={() => onDelete(mark)}
                className={cn(
                  "absolute -top-1 -right-1 size-5 place-items-center rounded-sm border border-line bg-panel text-ink-muted shadow-popover group-focus-within:grid group-hover:grid hover:text-ink",
                  current ? "grid" : "hidden",
                )}
              >
                <Icon name="close" />
              </button>
            </Tooltip>
          </li>
        );
      })}
    </ol>
  );
}
