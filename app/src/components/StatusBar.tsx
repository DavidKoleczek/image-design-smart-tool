import type { ImageListing, ImageSummary } from "@/lib/api";
import { dimensions } from "@/lib/format";
import { shortDirectory } from "@/lib/images";
import type { Shown } from "@/lib/viewed";

/** The line along the bottom: the image in view, the version of it that shows and its size, then the directory. */
export function StatusBar({
  listing,
  image,
  shown,
}: {
  listing: ImageListing | null;
  image: ImageSummary | null;
  shown: Shown | null;
}) {
  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 overflow-hidden border-t border-line bg-panel px-3 mono-annotation whitespace-nowrap text-ink-muted">
      <span className="truncate text-ink">
        {image ? image.name : "New image"}
      </span>
      {shown?.version && <span>{shown.version.id}</span>}
      {shown && shown.width !== null && shown.height !== null && (
        <span>{dimensions(shown.width, shown.height)}</span>
      )}
      {shown && shown.frames > 1 && <span>{shown.frames} frames</span>}
      <span className="flex-1" />
      {listing && (
        <span title={listing.directory} className="truncate">
          {shortDirectory(listing.directory)}
        </span>
      )}
    </footer>
  );
}
