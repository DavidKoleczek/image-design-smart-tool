import { useEffect, useRef, useState } from "react";

import { Export } from "@/components/Export";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import { Thumb } from "@/components/ui/thumb";
import { Tooltip } from "@/components/ui/tooltip";
import {
  restoreImageVersion,
  type ImageSummary,
  type ImageVersion,
} from "@/lib/api";
import { describe } from "@/lib/errors";
import { dimensions, methodLabel, usageLabel } from "@/lib/format";
import { filePicture, versionPicture, type Picture } from "@/lib/pictures";
import { isDrawing } from "@/lib/request";
import type { Runs } from "@/lib/runs";
import { ago, between } from "@/lib/time";
import { baseName } from "@/lib/paths";
import { cn } from "@/lib/utils";
import type { Shown } from "@/lib/viewed";

const PROMPT_SHOWN = 90;

/** What there is to say of what shows: its size, what made it, how long that took and what it used, and when. */
function facts(image: ImageSummary, shown: Shown, runs: Runs): string[] {
  const version = shown.version;
  const size =
    shown.width !== null && shown.height !== null
      ? [dimensions(shown.width, shown.height)]
      : [];
  const frames = shown.frames > 1 ? [`${shown.frames} frames`] : [];
  if (version === null) {
    const changed = image.modified ? [`changed ${ago(image.modified)}`] : [];
    return [...size, ...frames, ...changed];
  }
  const run = version.run_id !== null ? runs.get(version.run_id) : undefined;
  const usage = run ? usageLabel(run.usage) : null;
  return [
    version.id,
    ...size,
    ...frames,
    methodLabel(version.method),
    ...(run?.model ? [run.model] : []),
    ...(run?.finished ? [between(run.started, run.finished)] : []),
    ...(usage ? [usage] : []),
    ago(version.created),
  ];
}

function Tile({
  label,
  picture,
  shape,
  viewed,
  held,
  animated,
  about,
  onView,
}: {
  label: string;
  picture: Picture | null;
  shape: { width: number | null; height: number | null };
  viewed: boolean;
  /** Whether it is what the image's file holds. */
  held: boolean;
  animated: boolean;
  /** What made it, shown on hover. */
  about: string | null;
  onView: () => void;
}) {
  const button = useRef<HTMLButtonElement>(null);
  // The one that shows is brought into the strip, as when a new version lands past its end.
  useEffect(() => {
    if (viewed) {
      button.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [viewed]);
  const tile = (
    <button
      type="button"
      aria-current={viewed || undefined}
      onClick={onView}
      ref={button}
      className={cn(
        "flex shrink-0 cursor-default flex-col items-center gap-[3px] rounded-md border px-[3px] pt-[3px] pb-0.5 focus-visible:focus-ring focus-visible:outline-none",
        viewed
          ? "border-accent-ink bg-accent-soft text-ink"
          : "border-transparent text-ink-muted hover:bg-hover",
      )}
    >
      <Thumb
        picture={picture}
        shape={shape}
        animated={animated}
        className="size-14"
      />
      <span className="flex h-4 items-center gap-0.5 mono-annotation">
        {label}
        {held && <Icon name="check" label="In the image's file" />}
      </span>
    </button>
  );
  return about ? (
    <Tooltip content={about} side="top">
      {tile}
    </Tooltip>
  ) : (
    tile
  );
}

/**
 * The versions kept for the image in view, oldest first, under what there is to say of the one that shows. Picking
 * one shows it; Restore puts it back in the image's file. Each version a run has yet to make holds its place.
 */
export function Versions({
  image,
  shown,
  runs,
  pending,
  open,
  onOpenChange,
  onView,
  onRestored,
}: {
  image: ImageSummary;
  shown: Shown;
  runs: Runs;
  /** How many versions the run working on the image has yet to make. */
  pending: number;
  /** Whether the versions show under the header; folded, the header alone leaves the image more room. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Show the version with this id; null for what the image's file holds. */
  onView: (version: string | null) => void;
  onRestored: () => Promise<void>;
}) {
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A file that holds none of its versions, such as one changed by hand, shows beside them as itself.
  const loose =
    image.current === null &&
    image.modified !== null &&
    image.versions.length > 0;

  const restore = async (version: ImageVersion) => {
    setRestoring(true);
    setError(null);
    try {
      await restoreImageVersion(image.name, version.id);
      await onRestored();
      onView(null);
    } catch (cause) {
      setError(`Could not restore ${version.id}. ${describe(cause)}`);
    } finally {
      setRestoring(false);
    }
  };

  const about = (version: ImageVersion): string => {
    const prompt =
      version.run_id !== null ? runs.get(version.run_id)?.prompt : undefined;
    if (!prompt) {
      return methodLabel(version.method);
    }
    return prompt.length > PROMPT_SHOWN
      ? `${prompt.slice(0, PROMPT_SHOWN)}...`
      : prompt;
  };

  return (
    <section
      aria-label="Versions"
      className="shrink-0 border-t border-line bg-panel"
    >
      <header className="flex h-9 items-center gap-3 pr-2 pl-3 whitespace-nowrap">
        <h2 className="flex h-full">
          <button
            type="button"
            aria-expanded={open}
            onClick={() => onOpenChange(!open)}
            className="-ml-1 flex h-full cursor-default items-center gap-1 rounded-sm px-1 text-label focus-visible:focus-ring focus-visible:outline-none"
          >
            <Icon
              name="chevron"
              className={cn(
                "text-ink-muted transition-transform",
                !open && "-rotate-90",
              )}
            />
            Versions
          </button>
        </h2>
        <p className="flex min-w-0 flex-1 gap-3 overflow-hidden mono-annotation text-ink-muted">
          {facts(image, shown, runs).map((fact, index) => (
            <span key={index} className={cn(index === 0 && "text-ink")}>
              {fact}
            </span>
          ))}
        </p>
        {isDrawing(image.name) && shown.width !== null && (
          <Export image={image} shown={shown} />
        )}
        {shown.file
          ? shown.version && (
              <span className="flex min-w-0 shrink-0 items-center gap-1.5 pr-1 text-label">
                <Icon name="check" />
                Saved as
                <span className="max-w-40 truncate mono-value">
                  {baseName(image.name)}
                </span>
              </span>
            )
          : shown.version && (
              <Tooltip
                content={`Put ${shown.version.id} back in ${baseName(image.name)}`}
                side="top"
              >
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={restoring}
                  onClick={() => shown.version && void restore(shown.version)}
                >
                  <Icon name="undo" />
                  Restore
                </Button>
              </Tooltip>
            )}
      </header>
      {error && <Notice className="mx-3 mb-2">{error}</Notice>}
      {open && (image.versions.length > 0 || pending > 0) && (
        <div className="flex gap-1.5 overflow-x-auto px-3 pb-2">
          {image.versions.map((version) => (
            <Tile
              key={version.id}
              label={version.id}
              picture={versionPicture(image, version, true)}
              shape={version}
              viewed={shown.version?.id === version.id}
              held={image.current === version.id}
              animated={version.frames > 1}
              about={about(version)}
              onView={() => onView(version.id)}
            />
          ))}
          {loose && (
            <Tile
              label="file"
              picture={filePicture(image, true)}
              shape={image}
              viewed={shown.file}
              held
              animated={(image.frames ?? 1) > 1}
              about="Changed outside the app"
              onView={() => onView(null)}
            />
          )}
          {Array.from({ length: pending }, (_, index) => (
            <div
              key={index}
              className="flex shrink-0 flex-col items-center gap-[3px] border border-transparent px-[3px] pt-[3px] pb-0.5 text-ink-muted"
            >
              <span className="grid size-14 place-items-center rounded-sm border border-dashed border-line-control">
                <LoadingMark size={12} />
              </span>
              <span className="flex h-4 items-center mono-annotation">
                v{image.versions.length + index + 1}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
