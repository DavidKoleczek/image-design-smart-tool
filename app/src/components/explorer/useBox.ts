import {
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

/** A box drawn over the list, placed in the list's own scrolled space. */
export type Box = { left: number; top: number; width: number; height: number };

// How far the pointer moves with the button down before it is drawing a box rather than clicking.
const SLACK = 4;
// How near the top or bottom edge the pointer scrolls the list, and how far each frame at most.
const EDGE = 24;
const SCROLL = 14;

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/**
 * A box drawn by dragging from the blank space of a list, as a file manager selects with. The drag starts anywhere
 * in `list` but on a `data-handle`, which is for dragging the entry itself. `onStart` is called as a box starts, with
 * whether it adds to what is selected, and returns what to call with the `data-path` of everything the box touches
 * each time that changes.
 */
export function useBox(
  list: RefObject<HTMLElement | null>,
  onStart: (adding: boolean) => (touched: string[]) => void,
): {
  box: Box | null;
  start: (event: ReactPointerEvent) => void;
  /** Whether a box was just drawn, so the click that ends it is not taken for a click on what is under it. */
  drew: () => boolean;
} {
  const [box, setBox] = useState<Box | null>(null);
  const drawn = useRef(false);

  const start = (event: ReactPointerEvent) => {
    const element = list.current;
    const target = event.target as HTMLElement;
    if (
      !element ||
      event.button !== 0 ||
      !element.contains(target) ||
      target.closest("[data-handle], input, button") !== null
    ) {
      return;
    }
    const bounds = element.getBoundingClientRect();
    // Past the content is the scrollbar, which the drag is for.
    if (event.clientX - bounds.left >= element.clientWidth) {
      return;
    }
    const origin = {
      x: event.clientX - bounds.left + element.scrollLeft,
      y: event.clientY - bounds.top + element.scrollTop,
    };
    const from = { x: event.clientX, y: event.clientY };
    const adding = event.ctrlKey || event.metaKey;
    const pointerId = event.pointerId;
    let pointer = from;
    let touch: ((touched: string[]) => void) | null = null;
    let frame = 0;

    const draw = () => {
      const now = element.getBoundingClientRect();
      const x =
        clamp(pointer.x - now.left, 0, element.clientWidth) +
        element.scrollLeft;
      const y =
        clamp(pointer.y - now.top, 0, element.clientHeight) + element.scrollTop;
      const next = {
        left: Math.min(origin.x, x),
        top: Math.min(origin.y, y),
        width: Math.abs(x - origin.x),
        height: Math.abs(y - origin.y),
      };
      setBox(next);
      const touched: string[] = [];
      for (const each of element.querySelectorAll<HTMLElement>("[data-path]")) {
        const rect = each.getBoundingClientRect();
        const left = rect.left - now.left + element.scrollLeft;
        const top = rect.top - now.top + element.scrollTop;
        if (
          left < next.left + next.width &&
          left + rect.width > next.left &&
          top < next.top + next.height &&
          top + rect.height > next.top
        ) {
          touched.push(each.dataset.path ?? "");
        }
      }
      touch?.(touched);
    };

    const scroll = () => {
      const now = element.getBoundingClientRect();
      const past =
        pointer.y < now.top + EDGE
          ? pointer.y - now.top - EDGE
          : pointer.y > now.bottom - EDGE
            ? pointer.y - now.bottom + EDGE
            : 0;
      const before = element.scrollTop;
      element.scrollTop += clamp(past, -SCROLL, SCROLL);
      if (element.scrollTop !== before) {
        draw();
      }
      frame = requestAnimationFrame(scroll);
    };

    const move = (moved: PointerEvent) => {
      // The button was let go where the list did not hear of it.
      if ((moved.buttons & 1) === 0) {
        end();
        return;
      }
      pointer = { x: moved.clientX, y: moved.clientY };
      if (touch === null) {
        if (Math.hypot(pointer.x - from.x, pointer.y - from.y) < SLACK) {
          return;
        }
        touch = onStart(adding);
        drawn.current = true;
        // So the box goes on being drawn when the pointer leaves the list, or the frame the app is in.
        element.setPointerCapture(pointerId);
        frame = requestAnimationFrame(scroll);
      }
      draw();
    };

    const end = () => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", end);
      element.removeEventListener("pointercancel", end);
      cancelAnimationFrame(frame);
      setBox(null);
      // The click that the button's release makes comes before this.
      setTimeout(() => {
        drawn.current = false;
      });
    };

    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", end);
    element.addEventListener("pointercancel", end);
  };

  return { box, start, drew: () => drawn.current };
}
