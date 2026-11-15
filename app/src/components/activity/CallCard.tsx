import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { BESIDE, numbered, ROLE_ICONS, ROLE_LABELS } from "@/lib/calls";
import { usageLabel } from "@/lib/format";
import type { ImageCall } from "@/lib/thread";
import { between, useElapsed } from "@/lib/time";
import { cn } from "@/lib/utils";

function Elapsed({ since }: { since: string }) {
  return <>{useElapsed(since)}</>;
}

/** How a call stands, at the right of its card's first line. */
function State({ call }: { call: ImageCall }) {
  switch (call.state) {
    case "sending":
      return (
        <span className="flex items-center gap-1.5 mono-annotation text-accent-ink">
          <LoadingMark size={12} />
          <Elapsed since={call.started} />
        </span>
      );
    case "sent":
      return (
        <span className="flex items-center gap-1.5 mono-annotation text-ink-muted">
          <Icon name="check" />
          {call.finished && between(call.started, call.finished)}
        </span>
      );
    case "failed":
      return call.stopped ? (
        <span className="flex items-center gap-1.5 text-label text-ink-muted">
          <Icon name="stop" />
          Stopped
        </span>
      ) : (
        <span className="flex items-center gap-1.5 text-label text-danger">
          <Icon name="warning" />
          Failed
        </span>
      );
  }
}

/**
 * One request to an image model, where it was made in the conversation: what it sends at a glance, and how it went.
 * The whole card opens the call in full.
 */
export function CallCard({
  call,
  here,
  label,
  onOpen,
  onOpenImage,
}: {
  call: ImageCall;
  /** Whether the call is for the image whose conversation this is. */
  here: boolean;
  /** What a model is called, by its id. */
  label: (model: string) => string;
  onOpen: () => void;
  /** Bring up the image a call for another image is for. */
  onOpenImage: () => void;
}) {
  const images = numbered(call.images);
  const used = call.state === "sent" ? usageLabel(call.usage) : null;
  return (
    <div className="relative flex flex-col gap-1.5 rounded-md border border-line bg-panel p-2 hover:bg-hover">
      {/* Under the card's content, so the whole card opens the call. */}
      <button
        type="button"
        aria-label={`Open the image call for ${call.name}`}
        onClick={onOpen}
        className="absolute inset-0 rounded-md -outline-offset-2 focus-visible:focus-ring"
      />
      <div className="pointer-events-none relative flex min-w-0 items-center gap-2">
        <Icon name="image" className="shrink-0 text-ink-muted" />
        <span className="shrink-0 text-label">Image call</span>
        <span className="shrink-0 mono-annotation text-ink-muted">
          {call.edits ? "edit" : "create"}
        </span>
        <span className="min-w-0 truncate mono-annotation text-ink-muted">
          {label(call.model)}
        </span>
        <span className="flex-1" />
        <State call={call} />
      </div>
      {images.length > 0 && (
        <div className="pointer-events-none relative flex flex-wrap gap-1.5">
          {images.map((image, index) => (
            <span
              key={index}
              title={ROLE_LABELS[image.role]}
              className="relative"
            >
              {BESIDE.includes(image.role) ? (
                <span className="grid size-10 place-items-center rounded-sm border border-line bg-field text-ink-muted">
                  <Icon name={ROLE_ICONS[image.role]} size={20} />
                </span>
              ) : (
                <ReferenceThumb
                  reference={{ path: image.path }}
                  className="size-10"
                />
              )}
              {image.number !== null && (
                <span
                  className={cn(
                    "absolute bottom-0 left-0 rounded-tr-sm rounded-bl-sm px-1 mono-annotation",
                    image.role === "source"
                      ? "bg-accent text-on-accent"
                      : "bg-panel/90 text-ink",
                  )}
                >
                  {image.number}
                </span>
              )}
            </span>
          ))}
        </div>
      )}
      <p className="pointer-events-none relative line-clamp-3 wrap-break-word whitespace-pre-wrap">
        {call.prompt}
      </p>
      <div className="pointer-events-none relative flex flex-wrap items-center gap-x-2.5 gap-y-0.5 mono-annotation text-ink-muted">
        {call.parameters.map(([name, value]) => (
          <span key={name}>
            {name} <span className="text-ink">{value}</span>
          </span>
        ))}
        {used && <span>{used}</span>}
      </div>
      {call.error && !call.stopped && (
        <p className="pointer-events-none relative wrap-break-word text-danger">
          {call.error}
        </p>
      )}
      {!here && (
        <div className="relative flex min-w-0 items-center gap-1.5">
          <span className="text-caption text-ink-muted">For</span>
          <Button size="sm" onClick={onOpenImage} className="min-w-0">
            <span className="truncate mono-value">{call.name}</span>
            <Icon name="link-out" />
          </Button>
        </div>
      )}
    </div>
  );
}
