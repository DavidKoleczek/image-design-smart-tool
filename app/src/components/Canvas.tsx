import { useCallback, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { Icon } from "@/components/ui/icon";
import { Notice } from "@/components/ui/notice";
import { Versions } from "@/components/Versions";
import { Viewport } from "@/components/Viewport";
import type { ImageListing, ImageSummary, ImageVersion } from "@/lib/api";
import { previewPicture } from "@/lib/pictures";
import type { Runs } from "@/lib/runs";
import type { Shown } from "@/lib/viewed";

// Under this height, as inline in a host, the versions start folded to their header, so the image has the room.
const SHORT = 540;

/** The size a run was asked for, when it was asked for one. */
function askedSize(request: Record<string, unknown>): [number, number] | null {
  const size = request.size;
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
        }
      : null;
  const asked = typeof run?.request.count === "number" ? run.request.count : 1;
  const pending = run ? Math.max(0, asked - run.versions.length) : 0;
  return (
    <section
      ref={section}
      aria-label="Image"
      className="flex h-full min-w-0 flex-1 flex-col bg-canvas"
    >
      {error && <Notice className="m-3">{error}</Notice>}
      {image && shown ? (
        <>
          <Viewport
            key={image.name}
            image={image}
            shown={shown}
            before={before}
            live={live}
          />
          <Versions
            key={`versions:${image.name}`}
            image={image}
            shown={shown}
            runs={runs}
            pending={pending}
            open={versionsOpen ?? (height === 0 || height >= SHORT)}
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
