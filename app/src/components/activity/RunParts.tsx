import { Button } from "@/components/ui/button";
import { Dimension } from "@/components/ui/dimension";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import { ProgressBar } from "@/components/ui/progress-bar";
import type { ImageRunStatus, ImageUsage } from "@/lib/api";
import { effortLabel } from "@/lib/drawing";
import { usageLabel } from "@/lib/format";
import type { Call, Run } from "@/lib/thread";
import { between, timeOfDay, useElapsed } from "@/lib/time";

/**
 * Where a run starts: its number, when, the agent's model and effort, and whether it continued the conversation.
 */
export function RunDivider({
  run,
  label,
}: {
  run: Run;
  /** What a model is called, by its id. */
  label: (model: string) => string;
}) {
  const { model, reasoning_effort: effort, resumed } = run.request;
  const parts = [`Run ${run.number}`, timeOfDay(run.started)];
  if (typeof model === "string") {
    parts.push(label(model));
  }
  if (typeof effort === "string") {
    parts.push(effortLabel(effort).toLowerCase());
  }
  if (resumed) {
    parts.push("same conversation");
  } else if (run.kind === "agent" ? run.fresh : run.number > 1) {
    parts.push("new conversation");
  }
  return (
    <li className="shrink-0">
      <Dimension tone="control">
        <span className="flex gap-2">
          {parts.map((part, index) => (
            <span key={index}>{part}</span>
          ))}
        </span>
      </Dimension>
    </li>
  );
}

/** How a run ended, then what to do about it; its last words are already in what the agent said. */
export function RunResult({
  status,
  started,
  ended,
  error,
  usage,
}: {
  status: Exclude<ImageRunStatus, "running">;
  started: string;
  /** None for a run whose process stopped without saying how. */
  ended: string | null;
  error: string | null;
  usage: ImageUsage | null;
}) {
  const took = ended ? between(started, ended) : null;
  if (status === "done") {
    const used = usageLabel(usage);
    return (
      <li className="flex shrink-0 flex-wrap items-center gap-1.5">
        <Icon name="check" />
        <span className="text-label">Done in {took}</span>
        {used && <span className="mono-annotation text-ink-muted">{used}</span>}
      </li>
    );
  }
  if (status === "cancelled") {
    return (
      <li className="shrink-0">
        <Notice
          tone="neutral"
          title={took ? `Stopped after ${took}.` : "Stopped."}
        >
          Send a message to go on in the same conversation.
        </Notice>
      </li>
    );
  }
  const title = ended
    ? status === "timed-out"
      ? `Timed out after ${took}.`
      : `Failed after ${took}.`
    : "The run stopped unexpectedly.";
  const next = "Send a message to go on in the same conversation.";
  return (
    <li className="shrink-0">
      <Notice title={title}>{error ? `${error} ${next}` : next}</Notice>
    </li>
  );
}

/** Always in view while a run works, above the message box: how long it has been at it, the step it is on, and Stop. */
export function LiveStrip({
  since,
  current,
  stopping,
  onStop,
}: {
  since: string;
  current: { call: Call; number: number } | null;
  stopping: boolean;
  onStop: () => void;
}) {
  const elapsed = useElapsed(since);
  return (
    <div className="relative flex shrink-0 items-center gap-2.5 border-t border-line bg-accent-soft py-1.75 pr-2 pl-3">
      <ProgressBar className="-top-px" />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-center gap-2 text-label">
          <LoadingMark size={12} />
          {stopping ? "Stopping" : "Working"}
          <span className="mono-annotation text-ink">{elapsed}</span>
        </span>
        {current && (
          <span
            title={current.call.target}
            className="truncate mono-annotation text-ink-muted"
          >
            Step {current.number}, {current.call.doing.toLowerCase()}{" "}
            {current.call.target}
          </span>
        )}
      </div>
      <Button
        variant="secondary"
        size="sm"
        disabled={stopping}
        onClick={onStop}
      >
        <Icon name="stop" />
        Stop
      </Button>
    </div>
  );
}
