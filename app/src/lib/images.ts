import { useCallback, useEffect, useRef, useState } from "react";

import {
  listImages,
  showImage,
  type ImageListing,
  type ImageSummary,
} from "@/lib/api";
import { describe } from "@/lib/errors";
import { poll } from "@/lib/poll";

/** What is in view: an image by its name, or the new image being described. */
type Selection = { image: string } | "new";

/**
 * The images in the app's directory, polled, and which one is in view.
 *
 * The view opens on the image the app showed last, or the first one when it showed none. After that it changes when
 * the person picks an image or starts a new one, and when the server is asked to bring another image up, as `open_app`
 * from the host session does. An image made or changed anywhere else never takes the view.
 */
export function useImages(): {
  listing: ImageListing | null;
  /** The image in view; none while a new image is being described, or the directory has none. */
  image: ImageSummary | null;
  error: string | null;
  startNew: () => void;
  /** Bring the image into view, and record it as the one the app shows. */
  select: (name: string) => void;
  /** List the images now rather than at the next poll, as after a change made here. */
  refresh: () => Promise<void>;
} {
  const [listing, setListing] = useState<ImageListing | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The image the app shows as the server last had it; undefined before the first listing.
  const followed = useRef<string | null | undefined>(undefined);
  // Counts the picks made here as each starts and as it is recorded. A listing asked for across one may still have
  // the image shown before it, so it does not move the view.
  const picks = useRef(0);

  const refresh = useCallback(async () => {
    const asked = picks.current;
    try {
      const fresh = await listImages();
      if (asked === picks.current && fresh.shown !== followed.current) {
        followed.current = fresh.shown;
        if (fresh.shown !== null) {
          setSelection({ image: fresh.shown });
        }
      }
      setListing(fresh);
      setError(null);
    } catch (cause) {
      setError(`Could not list the images. ${describe(cause)}`);
    }
  }, []);

  useEffect(() => poll(refresh), [refresh]);

  const startNew = useCallback(() => setSelection("new"), []);

  const select = useCallback((name: string) => {
    setSelection({ image: name });
    picks.current += 1;
    showImage(name)
      .then(
        () => {
          followed.current = name;
        },
        () => {
          // It stays in view here; only the record of what the app shows is behind.
        },
      )
      .finally(() => {
        picks.current += 1;
      });
  }, []);

  const images = listing?.images ?? [];
  const picked =
    selection !== null && selection !== "new"
      ? images.find((image) => image.name === selection.image)
      : undefined;
  const image = selection === "new" ? null : (picked ?? images[0] ?? null);
  return { listing, image, error, startNew, select, refresh };
}

/** A directory as the app shows it, by its last two folders, such as `desk-study\.image-design`. */
export function shortDirectory(path: string): string {
  const separator = path.includes("\\") ? "\\" : "/";
  return path.split(separator).filter(Boolean).slice(-2).join(separator);
}
