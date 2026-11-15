import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { LargeImage } from "@/components/ReferencePreview";
import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Markdown } from "@/components/ui/markdown";
import { fileName } from "@/lib/references";
import type { Call } from "@/lib/thread";
import { cn } from "@/lib/utils";

type Section = { label: string; text: string; failed?: boolean };

// The arguments that say the most about each tool, under the label each shows with. A Read's file is already on its
// row. Any other tool shows all it was called with.
const SHOWN: Record<string, [string, string][]> = {
  Bash: [["command", "Command"]],
  commandExecution: [["command", "Command"]],
  Edit: [
    ["old_string", "Replaced"],
    ["new_string", "With"],
  ],
  Write: [["content", "Wrote"]],
  Read: [],
  imageView: [],
};

function sectionsOf(call: Call): Section[] {
  const shown = SHOWN[call.name];
  const changes = Array.isArray(call.input.changes)
    ? (call.input.changes as Record<string, unknown>[])
    : null;
  const sections: Section[] =
    call.name === "fileChange" && changes
      ? changes.flatMap((change) =>
          typeof change.diff === "string" && change.diff
            ? [{ label: "Changed", text: change.diff }]
            : [],
        )
      : shown
        ? shown.flatMap(([argument, label]) => {
            const value = call.input[argument];
            return typeof value === "string" && value
              ? [{ label, text: value }]
              : [];
          })
        : Object.keys(call.input).length > 0
          ? [
              {
                label: "Called with",
                text: JSON.stringify(call.input, null, 2),
              },
            ]
          : [];
  if (call.output) {
    sections.push({
      label: call.state === "failed" ? "Error" : "Output",
      text: call.output,
      failed: call.state === "failed",
    });
  }
  return sections;
}

function lines(sections: Section[]): number {
  return sections.reduce(
    (total, section) => total + section.text.split("\n").length,
    0,
  );
}

/**
 * Detail under a step's row, a few lines of it at first, and all of it, scrolling, once asked for. `lines` counts what
 * there is to show, for the person to judge before they ask.
 */
function Expandable({
  lines,
  children,
}: {
  lines?: number;
  children: ReactNode;
}) {
  const [all, setAll] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = box.current;
    if (!element) {
      return;
    }
    const measure = () =>
      setOverflows(element.scrollHeight > element.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [all]);

  return (
    <>
      <div className="relative">
        <div
          ref={box}
          className={cn(
            "flex flex-col gap-2 rounded-md border border-line bg-field px-2.5 py-2",
            all
              ? "max-h-[min(60vh,32rem)] overflow-auto"
              : "max-h-40 overflow-hidden",
          )}
        >
          {children}
        </div>
        {!all && overflows && (
          <div className="pointer-events-none absolute inset-x-px bottom-px h-10 rounded-b-md bg-linear-to-t from-field" />
        )}
      </div>
      {(all || overflows) && (
        <button
          type="button"
          onClick={() => setAll(!all)}
          className="mt-1 mono-annotation text-accent-ink hover:underline"
        >
          {all
            ? "Show less"
            : lines === undefined
              ? "Show all"
              : `Show all ${lines} lines`}
        </button>
      )}
    </>
  );
}

/** The image a step looked at, small, and large once it is clicked. */
function LookedAt({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const name = fileName(path);
  return (
    <>
      <button
        type="button"
        aria-label={`Show ${name} large`}
        title={path}
        onClick={() => setOpen(true)}
        className="block cursor-zoom-in rounded-sm focus-visible:focus-ring focus-visible:outline-none"
      >
        <ReferenceThumb reference={{ path }} className="size-24" />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title={name}
          subtitle={path}
          className="sm:h-full sm:max-w-400"
        >
          <div className="relative min-h-64 flex-1 bg-field">
            {open && <LargeImage path={path} name={name} />}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** A tool call in full under its row: what it was called with and what came back, or the image it looked at. */
export function CallDetail({ call }: { call: Call }) {
  const sections = sectionsOf(call);
  const note =
    call.output === null && call.state === "running"
      ? "Still running."
      : sections.length === 0 && call.looked === null
        ? "Nothing came back as text."
        : null;
  return (
    <div className="px-2 pb-2 pl-8">
      {call.looked !== null && <LookedAt path={call.looked} />}
      {sections.length > 0 && (
        <Expandable lines={lines(sections)}>
          {sections.map((section, index) => (
            <section key={index}>
              <h4 className="mb-0.5 mono-annotation text-ink-muted">
                {section.label}
              </h4>
              <pre
                className={cn(
                  "mono-value font-normal wrap-break-word whitespace-pre-wrap",
                  section.failed && "text-danger",
                )}
              >
                {section.text}
              </pre>
            </section>
          ))}
        </Expandable>
      )}
      {note && (
        <p
          className={cn(
            "mono-annotation text-ink-muted",
            sections.length > 0 && "mt-1.5",
          )}
        >
          {note}
        </p>
      )}
    </div>
  );
}

/** What the agent reasoned under its row, in the summary it gave of it. */
export function ReasoningDetail({ summary }: { summary: string }) {
  return (
    <div className="px-2 pb-2 pl-8">
      <Expandable>
        <Markdown className="text-label">{summary}</Markdown>
      </Expandable>
    </div>
  );
}
