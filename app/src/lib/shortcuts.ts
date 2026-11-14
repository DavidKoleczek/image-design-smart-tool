import { useEffect, useRef, type KeyboardEvent as KeyEvent } from "react";

/** What a key does, by the key as `KeyboardEvent.key` names it, lowercased. */
export type Shortcuts = Record<string, () => void>;

/** Whether a key pressed in `target` belongs to it rather than to the app: typing, or a popup's own keys. */
function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target.isContentEditable ||
    target.closest(
      "input, textarea, select, [role=dialog], [role=menu], [role=listbox]",
    ) !== null
  );
}

/** Whether Space pressed in `target` presses it, as it does a button, so it is not the app's to take. */
function pressed(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    target.closest(
      "button, a, summary, [role=button], [role=radio], [role=switch], [role=tab]",
    ) !== null
  );
}

/** Single keys that act on the app, only while focus is not in a field or a popup, so they never fight typing. */
export function useShortcuts(shortcuts: Shortcuts) {
  const latest = useRef(shortcuts);

  useEffect(() => {
    latest.current = shortcuts;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        event.isComposing ||
        typing(event.target) ||
        (event.key === " " && pressed(event.target))
      ) {
        return;
      }
      const action = latest.current[event.key.toLowerCase()];
      if (action) {
        event.preventDefault();
        action();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}

/** Keys on a file in a list, as a file manager takes them: Delete asks to delete it, F2 to rename it. */
export function fileKeys(
  onDelete: () => void,
  onRename: () => void,
): (event: KeyEvent) => void {
  return (event) => {
    if (event.ctrlKey || event.altKey || event.shiftKey) {
      return;
    }
    // Keyboards without a Delete key, as on many Macs, delete with Command and Backspace, as Finder does.
    if (event.metaKey ? event.key === "Backspace" : event.key === "Delete") {
      event.preventDefault();
      onDelete();
    } else if (event.key === "F2" && !event.metaKey) {
      event.preventDefault();
      onRename();
    }
  };
}
