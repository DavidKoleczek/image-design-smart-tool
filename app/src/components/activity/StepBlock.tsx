import { useState } from "react";

import { CallDetail, ReasoningDetail } from "@/components/activity/CallDetail";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import type { Call } from "@/lib/thread";
import { between, useElapsed } from "@/lib/time";
import { cn } from "@/lib/utils";

function Running({ since }: { since: string }) {
  return <>{useElapsed(since)}</>;
}

/**
 * One step: a plain verb, what it worked on, and how long it took; the running one counts up. A tool call opens to the
 * call in full, and reasoning to its summary.
 */
function ToolRow({
  call,
  open,
  onToggle,
}: {
  call: Call;
  open: boolean;
  onToggle: () => void;
}) {
  const running = call.state === "running";
  const failed = call.state === "failed";
  const verb = running ? call.doing : call.verb;
  const expandable = call.kind === "tool" || call.summary !== null;
  return (
    <li className="border-t border-line first:border-t-0">
      <div
        className={cn(
          "relative flex min-h-7 min-w-0 items-center gap-2 px-2",
          running && "bg-accent-soft",
        )}
      >
        {/* Under the row's content, so the whole row opens the step. */}
        {expandable && (
          <button
            type="button"
            aria-expanded={open}
            aria-label={`${verb} ${call.target}`.trim()}
            title={call.target}
            onClick={onToggle}
            className="absolute inset-0 -outline-offset-2 hover:bg-hover"
          />
        )}
        <Icon
          name={failed ? "warning" : call.icon}
          className={cn(
            "pointer-events-none relative",
            failed
              ? "text-danger"
              : running
                ? "text-accent-ink"
                : "text-ink-muted",
          )}
        />
        <span
          className={cn(
            "pointer-events-none relative shrink-0 text-label",
            failed && "text-danger",
          )}
        >
          {verb}
        </span>
        <span
          className={cn(
            "pointer-events-none relative min-w-0 flex-1 truncate text-ink-muted",
            call.kind === "reasoning" ? "text-label" : "mono-value",
          )}
        >
          {call.target}
        </span>
        <span
          className={cn(
            "pointer-events-none relative flex shrink-0 items-center gap-1.5 mono-annotation",
            running ? "text-accent-ink" : "text-ink-muted",
          )}
        >
          {running && <LoadingMark />}
          {running ? (
            <Running since={call.started} />
          ) : (
            call.finished && between(call.started, call.finished)
          )}
          <Icon
            name="chevron"
            className={cn(
              "text-ink-faint transition-transform",
              !open && "-rotate-90",
              !expandable && "invisible",
            )}
          />
        </span>
      </div>
      {open && call.summary !== null ? (
        <ReasoningDetail summary={call.summary} />
      ) : open && call.kind === "tool" ? (
        <CallDetail call={call} />
      ) : (
        call.error && (
          <p className="px-2 pb-2 pl-8 mono-value font-normal wrap-break-word whitespace-pre-wrap text-danger">
            {call.error}
          </p>
        )
      )}
    </li>
  );
}

/**
 * Consecutive steps between two messages: how many, how long, and whether they are still going. A call that failed
 * shows only on its own row, since the agent often goes on past one.
 */
export function StepBlock({
  calls,
  started,
  finished,
  state,
  open,
  onToggle,
}: {
  calls: Call[];
  started: string;
  finished: string | null;
  state: "running" | "done" | "failed";
  open: boolean;
  onToggle: () => void;
}) {
  const [shown, setShown] = useState<ReadonlySet<string>>(new Set());
  const toggle = (key: string) =>
    setShown((keys) => {
      const next = new Set(keys);
      if (!next.delete(key)) {
        next.add(key);
      }
      return next;
    });
  return (
    <li className="shrink-0 overflow-hidden rounded-md border border-line bg-panel">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex h-7 w-full items-center gap-1.5 px-2 text-left text-label -outline-offset-2 hover:bg-hover"
      >
        <Icon
          name="chevron"
          className={cn(
            "text-ink-muted transition-transform",
            !open && "-rotate-90",
          )}
        />
        {calls.length} {calls.length === 1 ? "step" : "steps"}
        <span className="mono-annotation text-ink-muted">
          {state === "running" ? (
            <Running since={started} />
          ) : (
            between(started, finished ?? started)
          )}
        </span>
        <span className="flex-1" />
        {state === "done" && !open && <Icon name="check" />}
        {state === "running" && !open && <LoadingMark />}
      </button>
      {open && (
        <ol className="border-t border-line">
          {calls.map((call) => (
            <ToolRow
              key={call.key}
              call={call}
              open={shown.has(call.key)}
              onToggle={() => toggle(call.key)}
            />
          ))}
        </ol>
      )}
    </li>
  );
}
