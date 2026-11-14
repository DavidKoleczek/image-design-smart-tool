import { useCallback, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { Icon } from "@/components/ui/icon";
import { Notice } from "@/components/ui/notice";
import { Timeline } from "@/components/Timeline";
import { ToolStrip } from "@/components/ToolStrip";
import { Versions } from "@/components/Versions";
import { Viewport } from "@/components/Viewport";
import type { ImageListing, ImageSummary, ImageVersion } from "@/lib/api";
import { useGuides, type CanvasMode } from "@/lib/canvas";
import { useDurations, usePlayback } from "@/lib/frames";
import { previewPicture } from "@/lib/pictures";
import type { Runs } from "@/lib/runs";
import type { Shown } from "@/lib/viewed";

// Under this height, as inline in a host, the versions start folded to their header, and so does an animation's
// timeline, so the image has the room.
const SHORT = 540;

/** The size a run was asked for, when it was asked for one: an image's size, or a drawing's canvas. */
function askedSize(request: Record<string, unknown>): [number, number] | null {
  const size = request.size ?? request.canvas;
  return Array.isArray(size) &&
    typeof size[0] === "number" &&
    typeof size[1] === "number"
    ? [size[0], size[1]]
    : null;
}

/** The middle of the workspace: the image in view, over the versions kept for it. */
export function Canvas({
  listing,
  image,
  shown,
  before,
  runs,
  mode,
  tools,
  blocked,
  steering,
  error,
  onView,
  onChanged,
}: {
  listing: ImageListing | null;
  /** The image in view; none for a new image, not generated yet. */
  image: ImageSummary | null;
  shown: Shown | null;
  before: ImageVersion | null;
  runs: Runs;
  /** What is drawn over the image to guide a request; null when it can take neither marks nor a mask. */
  mode: CanvasMode | null;
  /** The mode whose tools show, and why none of them can be used, when they cannot. */
  tools: CanvasMode;
  blocked: string | null;
  /** Whether marks can be drawn while a run works, for the next message to the agent drawing the image. */
  steering: boolean;
  error: string | null;
  /** Show the version with this id; null for what the image's file holds. */
  onView: (version: string | null) => void;
  /** Called once the image was changed from here, so it is listed again. */
  onChanged: () => Promise<void>;
}) {
  const [height, setHeight] = useState(0);
  // Whether the versions show, once the person has said; until then it goes by the room there is.
  const [versionsOpen, setVersionsOpen] = useState<boolean | null>(null);
  const section = useCallback((element: HTMLElement | null) => {
    if (!element) {
      return;
    }
    const observer = new ResizeObserver(([entry]) =>
      setHeight(entry.contentRect.height),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  // The run working on the image now: what it has sent so far, and what it has yet to make.
  const run = image?.status === "running" ? image.last_run : null;
  const latest = run ? runs.get(run.id)?.previews.at(-1) : undefined;
  const live =
    image && run
      ? {
          preview:
            latest !== undefined ? previewPicture(image, run.id, latest) : null,
          size: askedSize(run.request),
          steering,
        }
      : null;
  const asked = typeof run?.request.count === "number" ? run.request.count : 1;
  const pending = run ? Math.max(0, asked - run.versions.length) : 0;
  const whole = shown?.picture ?? null;
  const animated = shown !== null && shown.frames > 1 && whole !== null;
  const playback = usePlayback(image?.name ?? "", whole?.key ?? null, animated);
  const durations = useDurations(whole, animated);
  const guides = useGuides(image?.name ?? "", whole?.key ?? null);
  // A request starts from one frame of an animation, so its marks are on one frame: the one the first was drawn on.
  const marked =
    animated && mode === "markup" && guides.marks.length > 0
      ? guides.frame
      : null;
  const elsewhere =
    marked !== null && (playback.playing || playback.frame !== marked);
  const roomy = height === 0 || height >= SHORT;
  return (
    <section
      ref={section}
      aria-label="Image"
      className="flex h-full min-w-0 flex-1 flex-col bg-canvas"
    >
      {error && <Notice className="m-3">{error}</Notice>}
      {image && shown ? (
        <>
          <div className="flex min-h-0 flex-1">
            <ToolStrip
              mode={tools}
              blocked={
                blocked ??
                (run && !steering
                  ? "A request is working on this image"
                  : elsewhere && marked !== null
                    ? `The marks are on frame ${marked + 1}`
                    : null)
              }
            />
            <Viewport
              key={image.name}
              image={image}
              shown={shown}
              before={before}
              live={live}
              mode={mode}
              animation={
                animated
                  ? {
                      frame: Math.min(playback.frame, shown.frames - 1),
                      playing: playback.playing,
                      marked,
                    }
                  : null
              }
            />
          </div>
          {animated && (
            <Timeline
              key={`timeline:${image.name}`}
              of={whole}
              count={shown.frames}
              playback={playback}
              durations={durations}
              marked={marked}
              open={roomy}
            />
          )}
          <Versions
            key={`versions:${image.name}`}
            image={image}
            shown={shown}
            runs={runs}
            pending={pending}
            open={versionsOpen ?? roomy}
            onOpenChange={setVersionsOpen}
            onView={onView}
            onRestored={onChanged}
          />
        </>
      ) : (
        listing && (
          <div className="grid min-h-0 flex-1 place-items-center p-6">
            <EmptyState
              tile={<Icon name="image" size={24} />}
              tileClassName="bg-pastel-peach"
              title={
                listing.images.length === 0 ? "No images yet" : "New image"
              }
              className="w-full max-w-90"
            />
          </div>
        )
      )}
    </section>
  );
}
