import type { SentMark } from "@/lib/api";

export type MarkColor = "red" | "blue" | "yellow" | "black";

/** The colors a mark can have, by the names a request gives them, with the ink that reads on each. */
export const MARK_COLORS: { id: MarkColor; hex: string; on: string }[] = [
  { id: "red", hex: "#e5352b", on: "#ffffff" },
  { id: "blue", hex: "#1f6fd6", on: "#ffffff" },
  { id: "yellow", hex: "#f2b600", on: "#12161c" },
  { id: "black", hex: "#12161c", on: "#ffffff" },
];

export function markColor(id: MarkColor) {
  return MARK_COLORS.find((color) => color.id === id) ?? MARK_COLORS[0];
}

/** A place on the image, as fractions of its width and height from its top left. */
export type Point = [number, number];
export type Box = { x: number; y: number; w: number; h: number };

/** What a mark is, apart from its number: a circle or box by its bounds, an arrow by its ends, a sketch by its strokes. */
export type Shape =
  | ({ shape: "circle" } & Box)
  | ({ shape: "box" } & Box)
  | { shape: "arrow"; tail: Point; head: Point }
  | { shape: "sketch"; strokes: Point[][] };

export type MarkShape = Shape["shape"];

/** A mark on the image. Its number is its place among the image's marks, from 1. */
export type Mark = Shape & { id: number; color: MarkColor };
export type NewMark = Shape & { color: MarkColor };

const clamp = (value: number) => Math.min(1, Math.max(0, value));

export function clampPoint([x, y]: Point): Point {
  return [clamp(x), clamp(y)];
}

/** The part of the image a mark covers. */
export function markBox(mark: Shape): Box {
  if (mark.shape === "circle" || mark.shape === "box") {
    return { x: mark.x, y: mark.y, w: mark.w, h: mark.h };
  }
  const points =
    mark.shape === "arrow" ? [mark.tail, mark.head] : mark.strokes.flat();
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

/** The mark moved by a share of the image, stopped at the image's edges so it keeps its shape. */
export function moveMark<Moved extends Shape>(
  mark: Moved,
  dx: number,
  dy: number,
): Moved {
  const box = markBox(mark);
  const x = Math.min(1 - box.x - box.w, Math.max(-box.x, dx));
  const y = Math.min(1 - box.y - box.h, Math.max(-box.y, dy));
  const moved = ([px, py]: Point): Point => [px + x, py + y];
  if (mark.shape === "circle" || mark.shape === "box") {
    return { ...mark, x: mark.x + x, y: mark.y + y };
  }
  if (mark.shape === "arrow") {
    return { ...mark, tail: moved(mark.tail), head: moved(mark.head) };
  }
  return {
    ...mark,
    strokes: mark.strokes.map((stroke) => stroke.map(moved)),
  };
}

/** The mark as an SVG path on an image drawn `width` by `height`, with an arrow's head `head` long. */
export function markPath(
  mark: Shape,
  width: number,
  height: number,
  head = 14,
): string {
  if (mark.shape === "circle") {
    const rx = (mark.w / 2) * width;
    const ry = (mark.h / 2) * height;
    return `M${mark.x * width},${(mark.y + mark.h / 2) * height}a${rx},${ry} 0 1,0 ${rx * 2},0a${rx},${ry} 0 1,0 ${-rx * 2},0z`;
  }
  if (mark.shape === "box") {
    return `M${mark.x * width},${mark.y * height}h${mark.w * width}v${mark.h * height}h${-mark.w * width}z`;
  }
  if (mark.shape === "arrow") {
    const [x1, y1] = [mark.tail[0] * width, mark.tail[1] * height];
    const [x2, y2] = [mark.head[0] * width, mark.head[1] * height];
    const angle = Math.atan2(y2 - y1, x2 - x1);
    const barb = (turn: number) =>
      `${x2 - head * Math.cos(angle + turn)},${y2 - head * Math.sin(angle + turn)}`;
    return `M${x1},${y1}L${x2},${y2}M${barb(0.45)}L${x2},${y2}L${barb(-0.45)}`;
  }
  return mark.strokes
    .map(
      (stroke) =>
        stroke
          .map(
            ([x, y], index) => `${index ? "L" : "M"}${x * width},${y * height}`,
          )
          // A stroke of one point is a dot: a line of no length, which round caps still draw.
          .join("") + (stroke.length === 1 ? "h0" : ""),
    )
    .join("");
}

/** What a mark is called, for a person. */
export function markName(mark: Mark): string {
  return `Mark ${mark.id}, ${mark.color} ${mark.shape}`;
}

/** The mark as a request sends it. */
export function sentMark(mark: Shape & { color: MarkColor }): SentMark {
  if (mark.shape === "circle" || mark.shape === "box") {
    return {
      shape: mark.shape,
      points: [
        [mark.x, mark.y],
        clampPoint([mark.x + mark.w, mark.y + mark.h]),
      ],
      color: mark.color,
    };
  }
  if (mark.shape === "arrow") {
    return {
      shape: "arrow",
      points: [mark.tail, mark.head],
      color: mark.color,
    };
  }
  // A line takes two points, so a dot is sent as a line of no length.
  const [first, ...rest] = mark.strokes.map((stroke) =>
    stroke.length === 1 ? [stroke[0], stroke[0]] : stroke,
  );
  return {
    shape: "sketch",
    points: first,
    ...(rest.length > 0 ? { strokes: rest } : {}),
    color: mark.color,
  };
}
