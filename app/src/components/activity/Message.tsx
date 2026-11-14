import type { ReactNode } from "react";

import { ReferenceThumb } from "@/components/ReferenceThumb";
import { markColor } from "@/lib/marks";
import type { Block, Chip } from "@/lib/thread";
import { cn } from "@/lib/utils";

/** A mark a message carried: its number in the mark's color, and its shape. */
export function MarkChip({
  chip,
  children,
}: {
  chip: Extract<Chip, { kind: "mark" }>;
  /** What follows the shape, such as a button that takes it off a message not yet sent. */
  children?: ReactNode;
}) {
  const color = markColor(chip.color);
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-line bg-panel pr-1.5 pl-0.5">
      <span
        style={{ background: color.hex, color: color.on }}
        className="grid size-4.5 shrink-0 place-items-center rounded-sm mono-annotation"
      >
        {chip.number}
      </span>
      <span className="mono-annotation">{chip.shape}</span>
      {children}
    </span>
  );
}

/** What someone asked of the drawing, or told its agent while it worked, with the marks and references it carried. */
export function Message({
  block,
}: {
  block: Extract<Block, { kind: "message" }>;
}) {
  const marks = block.chips.filter((chip) => chip.kind === "mark");
  const references = block.chips.filter((chip) => chip.kind === "reference");
  return (
    <li className="flex max-w-[86%] shrink-0 flex-col items-end gap-1 self-end">
      <span className="text-caption text-ink-muted">{block.sender}</span>
      <p
        className={cn(
          "rounded-lg border bg-field px-3 py-1.5 wrap-break-word whitespace-pre-wrap",
          block.steering ? "border-line-control" : "border-line",
        )}
      >
        {block.text}
      </p>
      {block.chips.length > 0 && (
        <div className="flex flex-wrap items-end justify-end gap-1">
          {marks.map((chip, index) => (
            <MarkChip key={index} chip={chip} />
          ))}
          {references.map((chip) => (
            <span key={chip.path} title={chip.label}>
              <ReferenceThumb
                reference={{ path: chip.path }}
                className="size-10"
              />
            </span>
          ))}
        </div>
      )}
      {block.failed && (
        <span className="text-caption text-danger">
          Not delivered. {block.failed}
        </span>
      )}
    </li>
  );
}
