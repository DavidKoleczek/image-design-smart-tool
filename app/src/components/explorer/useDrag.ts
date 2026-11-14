import {
  useEffect,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

import { hasFiles } from "@/lib/drops";

/** What is being dragged over the list. */
export type Dragging = {
  /** The entries of the list being dragged, by their paths; none for files from outside it. */
  paths: string[];
  /** The folder a drop now would put them in, "" for the top; null where they cannot be dropped. */
  into: string | null;
  /** Whether a drop copies rather than moves. */
  copy: boolean;
};

type Options = {
  /** What a drag that starts on the entry takes with it; nothing for no drag. */
  take: (path: string) => string[];
  /** The folder a drop on the entry lands in. */
  folderAt: (path: string) => string;
  /** Whether a drop of the entries into the folder would do anything. */
  allows: (paths: string[], folder: string, copy: boolean) => boolean;
  /** The pointer has stayed over the entry while dragging, which opens a closed folder. */
  onHold: (path: string) => void;
  onDrop: (paths: string[], folder: string, copy: boolean) => void;
  /** Files from outside were dropped on the folder. */
  onFiles: (transfer: DataTransfer, folder: string) => void;
};

// How far the pointer moves with the button down before it is dragging rather than clicking.
const SLACK = 4;
const HOLD_MS = 600;
// How near the top or bottom edge the pointer scrolls the list, and how far each frame at most.
const EDGE = 24;
const SCROLL = 14;

function pathAt(target: Element | null): string | null {
  return target?.closest<HTMLElement>("[data-path]")?.dataset.path ?? null;
}

/** The folder whose part of the list `target` is in, where the list marks one with `data-folder`, else the top. */
function sectionAt(target: Element | null): string {
  return target?.closest<HTMLElement>("[data-folder]")?.dataset.folder ?? "";
}

/**
 * Entries of a list dragged to another folder of it, on pointer events, and files dragged in from outside, which
 * arrive as the browser's own drag. A drag of an entry starts on its `data-handle`. A drop lands in the folder under
 * the pointer: a folder's own entry, the folder a file is in, and for the space between and under the entries the
 * folder a `data-folder` around it names, or the top.
 */
export function useDrag(
  list: RefObject<HTMLElement | null>,
  options: Options,
): {
  dragging: Dragging | null;
  start: (event: ReactPointerEvent) => void;
  /** Whether a drag just ended, so the click that ends it is not taken for a click on what is under it. */
  dragged: () => boolean;
  /** Give it what shows what is dragged, which is then kept at the pointer. */
  ghost: (element: HTMLElement | null) => void;
  /** The list's handlers for files dragged in from outside. */
  files: {
    onDragOver: (event: ReactDragEvent) => void;
    onDragLeave: (event: ReactDragEvent) => void;
    onDrop: (event: ReactDragEvent) => void;
  };
} {
  const [dragging, setDragging] = useState<Dragging | null>(null);
  const latest = useRef(options);
  const done = useRef(false);
  const shown = useRef<HTMLElement | null>(null);
  const pointer = useRef({ x: 0, y: 0 });
  const held = useRef<{ path: string | null; timer: number }>({
    path: null,
    timer: 0,
  });

  useEffect(() => {
    latest.current = options;
  });

  const place = () => {
    if (shown.current) {
      shown.current.style.transform = `translate(${pointer.current.x + 14}px, ${pointer.current.y + 10}px)`;
    }
  };

  /** Note the entry the pointer is over, so one it stays over is told after a while. */
  const hover = (path: string | null) => {
    if (held.current.path === path) {
      return;
    }
    window.clearTimeout(held.current.timer);
    held.current = {
      path,
      timer:
        path === null
          ? 0
          : window.setTimeout(() => latest.current.onHold(path), HOLD_MS),
    };
  };

  const scroll = (element: HTMLElement, x: number, y: number) => {
    const bounds = element.getBoundingClientRect();
    if (x < bounds.left || x > bounds.right) {
      return;
    }
    const past =
      y < bounds.top + EDGE
        ? y - bounds.top - EDGE
        : y > bounds.bottom - EDGE
          ? y - bounds.bottom + EDGE
          : 0;
    element.scrollTop += Math.min(SCROLL, Math.max(-SCROLL, past));
  };

  const start = (event: ReactPointerEvent) => {
    const element = list.current;
    const target = event.target as HTMLElement;
    if (
      !element ||
      event.button !== 0 ||
      !element.contains(target) ||
      target.closest("input, button, [data-toggle]") !== null
    ) {
      return;
    }
    const path = pathAt(target.closest("[data-handle]"));
    if (path === null) {
      return;
    }
    const from = { x: event.clientX, y: event.clientY };
    const pointerId = event.pointerId;
    // Option copies on a Mac, where Control with a click is a right click.
    let copy = event.ctrlKey || event.altKey;
    let paths: string[] | null = null;
    let now: Dragging | null = null;
    let frame = 0;

    const update = () => {
      if (paths === null) {
        return;
      }
      const { x, y } = pointer.current;
      const under = document.elementFromPoint(x, y);
      const inside = under !== null && element.contains(under);
      const over = inside ? pathAt(under) : null;
      const folder =
        over === null ? sectionAt(under) : latest.current.folderAt(over);
      const into =
        inside && latest.current.allows(paths, folder, copy) ? folder : null;
      hover(over);
      element.style.cursor = into === null ? "no-drop" : copy ? "copy" : "";
      if (now === null || now.into !== into || now.copy !== copy) {
        now = { paths, into, copy };
        setDragging(now);
      }
      place();
    };

    const tick = () => {
      scroll(element, pointer.current.x, pointer.current.y);
      // What is under the pointer changes as the list scrolls, and as a folder opens.
      update();
      frame = requestAnimationFrame(tick);
    };

    const end = (drop: boolean) => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key, true);
      window.removeEventListener("keyup", key, true);
      cancelAnimationFrame(frame);
      hover(null);
      element.style.cursor = "";
      if (paths === null) {
        return;
      }
      if (drop && now !== null && now.into !== null) {
        latest.current.onDrop(paths, now.into, now.copy);
      }
      setDragging(null);
      // The click that the button's release makes comes before this.
      setTimeout(() => {
        done.current = false;
      });
    };

    const move = (moved: PointerEvent) => {
      // The button was let go where the list did not hear of it.
      if ((moved.buttons & 1) === 0) {
        end(false);
        return;
      }
      pointer.current = { x: moved.clientX, y: moved.clientY };
      copy = moved.ctrlKey || moved.altKey;
      if (paths === null) {
        if (
          Math.hypot(moved.clientX - from.x, moved.clientY - from.y) < SLACK
        ) {
          return;
        }
        const taken = latest.current.take(path);
        if (taken.length === 0) {
          end(false);
          return;
        }
        paths = taken;
        done.current = true;
        // So the drag goes on when the pointer leaves the list, or the frame the app is in.
        element.setPointerCapture(pointerId);
        window.addEventListener("keydown", key, true);
        window.addEventListener("keyup", key, true);
        frame = requestAnimationFrame(tick);
      }
      update();
    };

    const up = (released: PointerEvent) => {
      pointer.current = { x: released.clientX, y: released.clientY };
      update();
      end(true);
    };

    const cancel = () => end(false);

    const key = (pressed: KeyboardEvent) => {
      if (pressed.key === "Escape") {
        pressed.preventDefault();
        pressed.stopPropagation();
        end(false);
        return;
      }
      copy = pressed.ctrlKey || pressed.altKey;
      update();
    };

    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", cancel);
  };

  const files = {
    onDragOver(event: ReactDragEvent) {
      const element = list.current;
      if (!element || !hasFiles(event.dataTransfer)) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      const target = event.target as Element;
      const over = pathAt(target);
      const into =
        over === null ? sectionAt(target) : latest.current.folderAt(over);
      hover(over);
      scroll(element, event.clientX, event.clientY);
      setDragging((before) =>
        before !== null && before.paths.length === 0 && before.into === into
          ? before
          : { paths: [], into, copy: true },
      );
    },
    onDragLeave(event: ReactDragEvent) {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
        hover(null);
        setDragging(null);
      }
    },
    onDrop(event: ReactDragEvent) {
      if (!hasFiles(event.dataTransfer)) {
        return;
      }
      event.preventDefault();
      hover(null);
      setDragging(null);
      const target = event.target as Element;
      const over = pathAt(target);
      latest.current.onFiles(
        event.dataTransfer,
        over === null ? sectionAt(target) : latest.current.folderAt(over),
      );
    },
  };

  return {
    dragging,
    start,
    dragged: () => done.current,
    ghost: (element) => {
      shown.current = element;
      place();
    },
    files,
  };
}
