import { EmptyState } from "@/components/ui/empty-state";
import { Icon } from "@/components/ui/icon";
import { Notice } from "@/components/ui/notice";
import { Versions } from "@/components/Versions";
import { Viewport } from "@/components/Viewport";
import type { ImageListing, ImageSummary, ImageVersion } from "@/lib/api";
import { useRuns } from "@/lib/runs";
import type { Shown } from "@/lib/viewed";

/** The middle of the workspace: the image in view, over the versions kept for it. */
export function Canvas({
  listing,
  image,
  shown,
  before,
  error,
  onView,
  onChanged,
}: {
  listing: ImageListing | null;
  /** The image in view; none for a new image, not generated yet. */
  image: ImageSummary | null;
  shown: Shown | null;
  before: ImageVersion | null;
  error: string | null;
  /** Show the version with this id; null for what the image's file holds. */
  onView: (version: string | null) => void;
  /** Called once the image was changed from here, so it is listed again. */
  onChanged: () => Promise<void>;
}) {
  const runs = useRuns(image);
  return (
    <section
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
          />
          <Versions
            key={`versions:${image.name}`}
            image={image}
            shown={shown}
            runs={runs}
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
