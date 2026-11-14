import { useEffect, useRef, useState } from "react";

import { nameProblem } from "@/lib/paths";
import { cn } from "@/lib/utils";

/**
 * A name typed in place of the one an entry shows. Enter, or leaving the field, keeps it. Escape drops it. A name no
 * file system takes says why under the field, and is not kept.
 */
export function NameField({
  name,
  extension = "",
  onKeep,
  onDrop,
  className,
}: {
  /** The name as the field starts, all of it selected. */
  name: string;
  /** What follows the name and is not for changing, such as a file's `.png`. */
  extension?: string;
  /** Called with the name typed, and whether a key kept it rather than the field being left. */
  onKeep: (typed: string, byKey: boolean) => void;
  onDrop: (byKey: boolean) => void;
  className?: string;
}) {
  const [value, setValue] = useState(name);
  const input = useRef<HTMLInputElement>(null);
  // Keeping or dropping the name takes the field away, which a browser may report as the field being left.
  const settled = useRef(false);
  const problem =
    value.trim() === "" ? null : nameProblem(value.trim() + extension);

  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);

  const settle = (keep: boolean, byKey: boolean) => {
    if (settled.current) {
      return;
    }
    settled.current = true;
    if (keep) {
      onKeep(value, byKey);
    } else {
      onDrop(byKey);
    }
  };

  return (
    <span
      className={cn("relative flex min-w-0 flex-1 items-center", className)}
    >
      <input
        ref={input}
        value={value}
        aria-label="Name"
        aria-invalid={problem !== null}
        spellCheck={false}
        autoComplete="off"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.stopPropagation();
            if (problem === null) {
              settle(true, true);
            }
          } else if (event.key === "Escape") {
            event.stopPropagation();
            settle(false, true);
          }
        }}
        onBlur={() => settle(problem === null, false)}
        className="-mx-1 h-5 min-w-12 flex-1 rounded-[2px] border border-ink bg-panel px-0.75 font-normal text-ink outline-none select-text aria-invalid:border-danger"
      />
      {extension && <span className="ml-1 text-ink-muted">{extension}</span>}
      {problem && (
        <span
          role="alert"
          className="absolute top-full left-0 z-20 mt-1 w-max max-w-56 rounded-md bg-raised px-2 py-1 text-caption font-normal tracking-normal whitespace-normal text-danger shadow-popover"
        >
          {problem}
        </span>
      )}
    </span>
  );
}
