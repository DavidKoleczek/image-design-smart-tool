import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

// How far the pointer moves with the button down before it is dragging rather than clicking, as in Your images.
const SLACK = 4;

/** `items` with the one at `from` taken out and put at `to`, or `items` itself when that leaves them as they are. */
export function moved<Item>(items: Item[], from: number, to: number): Item[] {
  const target = Math.min(items.length - 1, Math.max(0, to));
  if (from < 0 || from >= items.length || from === target) {
    return items;
  }
  const list = items.slice();
  list.splice(target, 0, list.splice(from, 1)[0]);
  return list;
}

/**
 * The items of a list put in another order by dragging one along it, on pointer events. The list's children are its
 * items, in order, laid out across it when `across`, else down it. Once the pointer has moved a little with the button
 * down, the item dragged goes to the place of whichever item the pointer passes the middle of. Escape puts it back.
 */
export function useReorder(
  list: RefObject<HTMLElement | null>,
  across: boolean,
  onMove: (id: string, index: number) => void,
): {
  /** The item being dragged, by its id. */
  dragging: string | null;
  /** Hand it the press on an item, which a drag may start from. */
  start: (id: string, event: ReactPointerEvent) => void;
  /** Whether a drag just ended, so the click that ends it is not taken for a click on the item. */
  dragged: () => boolean;
} {
  const [dragging, setDragging] = useState<string | null>(null);
  const latest = useRef(onMove);
  useEffect(() => {
    latest.current = onMove;
  });
  const done = useRef(false);

  const start = (id: string, event: ReactPointerEvent) => {
    const element = list.current;
    const pressed = event.currentTarget;
    const item = [...(element?.children ?? [])].find((child) =>
      child.contains(pressed),
    );
    if (!element || !item || event.button !== 0) {
      return;
    }
    const from = { x: event.clientX, y: event.clientY };
    const pointerId = event.pointerId;
    const before = [...element.children].indexOf(item);
    let begun = false;

    const place = (x: number, y: number) => {
      const index = [...element.children].filter((child) => {
        if (child === item) {
          return false;
        }
        const box = child.getBoundingClientRect();
        return across
          ? x > box.left + box.width / 2
          : y > box.top + box.height / 2;
      }).length;
      latest.current(id, index);
    };

    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key, true);
      if (!begun) {
        return;
      }
      setDragging(null);
      // The click that the button's release makes comes before this.
      setTimeout(() => {
        done.current = false;
      });
    };

    const cancel = () => {
      if (begun) {
        latest.current(id, before);
      }
      end();
    };

    const move = (moving: PointerEvent) => {
      // The button was let go where the list did not hear of it.
      if ((moving.buttons & 1) === 0) {
        end();
        return;
      }
      if (!begun) {
        if (
          Math.hypot(moving.clientX - from.x, moving.clientY - from.y) < SLACK
        ) {
          return;
        }
        begun = true;
        done.current = true;
        setDragging(id);
        // So the drag goes on when the pointer leaves the frame the app is in.
        if (item.isConnected) {
          item.setPointerCapture(pointerId);
        }
        window.addEventListener("keydown", key, true);
      }
      place(moving.clientX, moving.clientY);
    };

    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        cancel();
      }
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", cancel);
  };

  return { dragging, start, dragged: () => done.current };
}
