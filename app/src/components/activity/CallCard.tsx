import { useState } from "react";

import { ExpandableThumb, ImageViewer } from "@/components/ImageViewer";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Thumb } from "@/components/ui/thumb";
import { BESIDE, numbered, ROLE_ICONS, ROLE_LABELS } from "@/lib/calls";
import { usageLabel } from "@/lib/format";
import { previewPicture } from "@/lib/pictures";
import { fileName } from "@/lib/references";
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
 * The whole card opens the call in full, and an image it sends shows large once clicked.
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
  const [shown, setShown] = useState<string | null>(null);
  const draft = call.draft?.made ? call.draft : null;
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
        {call.draft && (
          <span className="shrink-0 rounded-sm bg-accent-soft px-1 mono-annotation text-accent-ink">
            draft
          </span>
        )}
        <span className="min-w-0 truncate mono-annotation text-ink-muted">
          {label(call.model)}
        </span>
        <span className="flex-1" />
        <State call={call} />
      </div>
      {images.length > 0 && (
        <div className="pointer-events-none relative flex flex-wrap gap-1.5">
          {images.map((image, index) => {
            const number = image.number !== null && (
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
            );
            return BESIDE.includes(image.role) ? (
              <span
                key={index}
                title={ROLE_LABELS[image.role]}
                className="relative"
              >
                <span className="grid size-10 place-items-center rounded-sm border border-line bg-field text-ink-muted">
                  <Icon name={ROLE_ICONS[image.role]} size={20} />
                </span>
                {number}
              </span>
            ) : (
              <ExpandableThumb
                key={index}
                path={image.path}
                label={ROLE_LABELS[image.role]}
                onExpand={() => setShown(image.path)}
                className="size-10"
              >
                {number}
              </ExpandableThumb>
            );
          })}
        </div>
      )}
      {/* The canvas shows what a call for this image has made so far, so only one for another image, or a draft,
          which the canvas leaves out, shows it here. */}
      {(!here || call.draft) && call.preview !== null && (
        <div className="pointer-events-none relative flex items-end gap-2">
          <Thumb
            picture={previewPicture({ name: call.name }, call.id, call.preview)}
            className="size-24"
          />
          <span className="mono-annotation text-ink-muted">So far</span>
        </div>
      )}
      {draft && (
        <div className="pointer-events-none relative flex items-end gap-2">
          <ExpandableThumb
            path={draft.path}
            label="Draft"
            onExpand={() => setShown(draft.path)}
            className="size-24"
          />
          <span className="mono-annotation text-ink-muted">
            {call.versions.length > 0
              ? `Draft, kept as ${call.versions.join(", ")}`
              : "Draft"}
          </span>
        </div>
      )}
      <ImageViewer
        items={[
          ...images
            .filter((image) => !BESIDE.includes(image.role))
            .map((image) => ({ path: image.path, name: fileName(image.path) })),
          ...(draft ? [{ path: draft.path, name: "Draft" }] : []),
        ]}
        path={shown}
        onShow={setShown}
      />
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
