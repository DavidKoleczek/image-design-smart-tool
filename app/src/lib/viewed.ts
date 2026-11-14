import { useCallback, useState } from "react";

import type { ImageSummary, ImageVersion } from "@/lib/api";
import { filePicture, versionPicture, type Picture } from "@/lib/pictures";

/** What of an image the canvas shows: what its file holds, or a version kept for it. */
export type Shown = {
  /** Whether it is what the image's file holds, rather than an earlier or later version. */
  file: boolean;
  /** The version it is; none for a file that holds none of them, such as one changed by hand. */
  version: ImageVersion | null;
  /** Null for a file that is missing, or not an image the tool can read. */
  width: number | null;
  height: number | null;
  frames: number;
  picture: Picture | null;
};

function shownOf(image: ImageSummary, viewing: string | null): Shown {
  const picked =
    viewing !== null && viewing !== image.current
      ? image.versions.find((version) => version.id === viewing)
      : undefined;
  if (picked) {
    return {
      file: false,
      version: picked,
      width: picked.width,
      height: picked.height,
      frames: picked.frames,
      picture: versionPicture(image, picked),
    };
  }
  return {
    file: true,
    version:
      image.versions.find((version) => version.id === image.current) ?? null,
    width: image.width,
    height: image.height,
    frames: image.frames ?? 1,
    picture: filePicture(image),
  };
}

/** The version before what shows: the one made before it, or the last one kept for a file changed since. */
function beforeOf(image: ImageSummary, shown: Shown): ImageVersion | null {
  if (shown.version) {
    const index = image.versions.indexOf(shown.version);
    return index > 0 ? image.versions[index - 1] : null;
  }
  return image.versions.at(-1) ?? null;
}

/**
 * Which version of the image in view shows. It starts on what the image's file holds, and goes back to that when
 * another image comes into view.
 */
export function useViewed(image: ImageSummary | null): {
  shown: Shown | null;
  before: ImageVersion | null;
  /** Show the version with this id; null for what the image's file holds. */
  view: (version: string | null) => void;
} {
  const [viewing, setViewing] = useState<{
    image: string;
    version: string;
  } | null>(null);
  const name = image?.name ?? null;

  const view = useCallback(
    (version: string | null) =>
      setViewing(
        name !== null && version !== null ? { image: name, version } : null,
      ),
    [name],
  );

  if (image === null) {
    return { shown: null, before: null, view };
  }
  const shown = shownOf(
    image,
    viewing?.image === image.name ? viewing.version : null,
  );
  return { shown, before: beforeOf(image, shown), view };
}
