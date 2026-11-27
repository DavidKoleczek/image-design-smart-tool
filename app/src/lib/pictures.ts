import { useEffect, useState } from "react";

import {
  readImageFrame,
  readImagePicture,
  readRunPreview,
  type ImageSummary,
  type ImageVersion,
} from "@/lib/api";
import { describe } from "@/lib/errors";

/** What of an image to show. */
export type Picture = {
  name: string;
  /** The version kept for the image; null for its file, and for a run's in-progress image. */
  version: string | null;
  /** A thumbnail rather than the image itself. */
  small: boolean;
  /** For an in-progress image of a run: the run's id, and the index the image has among the run's previews. */
  preview: { run: string; index: number } | null;
  /** For one frame of an animation: its index from 0. */
  frame?: number;
  /**
   * What tells its content from any other: the hash of the file or version, so the same content is read once however
   * it is reached, or the run and index of an in-progress image.
   */
  key: string;
};

/** The image's file; nothing when it has none the tool can read. */
export function filePicture(
  image: ImageSummary,
  small = false,
): Picture | null {
  return image.width === null || image.sha256 === null
    ? null
    : {
        name: image.name,
        version: null,
        small,
        preview: null,
        key: image.sha256,
      };
}

export function versionPicture(
  image: ImageSummary,
  version: ImageVersion,
  small = false,
): Picture {
  return {
    name: image.name,
    version: version.id,
    small,
    preview: null,
    key: version.sha256,
  };
}

/** An in-progress image a run on the image sent before its final one. */
export function previewPicture(
  image: Pick<ImageSummary, "name">,
  run: string,
  index: number,
): Picture {
  return {
    name: image.name,
    version: null,
    small: false,
    preview: { run, index },
    key: `preview:${run}:${index}`,
  };
}

/** One frame of an animation, which `of` is as a whole. */
export function framePicture(
  of: Picture,
  frame: number,
  small = false,
): Picture {
  return { ...of, small, frame, key: `${of.key}#${frame}` };
}

type Entry = { promise: Promise<string>; url: string | null };

// Thumbnails are a few kilobytes each, so a directory's worth stays; a full image can be megabytes, so only the last
// few looked at do, enough to go back and forth between versions without reading them again. An animation's frames
// are kept apart from those, so playing one through does not push out the images around it.
const KEPT = { small: 600, full: 12, frames: 96 };
const caches = {
  small: new Map<string, Entry>(),
  full: new Map<string, Entry>(),
  frames: new Map<string, Entry>(),
};

function cacheOf(picture: Picture): Map<string, Entry> {
  return picture.small
    ? caches.small
    : picture.frame === undefined
      ? caches.full
      : caches.frames;
}

// At most this many thumbnails are read at once, so the image in view is not read behind a directory of them.
const SMALL_AT_ONCE = 4;
let reading = 0;
const waiting: (() => void)[] = [];

function inTurn(read: () => Promise<string>): Promise<string> {
  return new Promise((resolve, reject) => {
    const start = () => {
      reading += 1;
      read()
        .then(resolve, reject)
        .finally(() => {
          reading -= 1;
          waiting.shift()?.();
        });
    };
    if (reading < SMALL_AT_ONCE) {
      start();
    } else {
      waiting.push(start);
    }
  });
}

function entryOf(picture: Picture): Entry {
  const cache = cacheOf(picture);
  const key = picture.key;
  const kept = cache.get(key);
  if (kept) {
    // Put back as the newest, so what is still looked at is the last to go.
    cache.delete(key);
    cache.set(key, kept);
    return kept;
  }
  const { preview, frame } = picture;
  const read = () =>
    preview
      ? readRunPreview(picture.name, preview.run, preview.index)
      : frame !== undefined
        ? readImageFrame(picture.name, picture.version, frame, picture.small)
        : readImagePicture(picture.name, picture.version, picture.small);
  const entry: Entry = {
    promise: picture.small ? inTurn(read) : read(),
    url: null,
  };
  entry.promise.then(
    (url) => {
      entry.url = url;
    },
    // A failed read is tried again next time.
    () => cache.delete(key),
  );
  cache.set(key, entry);
  const most = picture.small
    ? KEPT.small
    : frame === undefined
      ? KEPT.full
      : KEPT.frames;
  for (const old of cache.keys()) {
    if (cache.size <= most) {
      break;
    }
    cache.delete(old);
  }
  return entry;
}

/** Read the picture ahead of when it shows, and say once it has been read, or that it could not be. */
export function readAhead(picture: Picture): Promise<unknown> {
  return entryOf(picture).promise;
}

type Loaded = { picture: Picture; url: string | null; error: string | null };

/**
 * The picture read through the host: its data URL once read, or why it could not be.
 *
 * Some pictures keep showing what showed of the same image until the new one is read. A thumbnail does, so a row does
 * not blink each time its image changes. An in-progress image and what comes before or after it do, so an image
 * forms without going blank. A frame of an animation does, so it plays without going blank.
 */
export function usePicture(picture: Picture | null): {
  url: string | null;
  error: string | null;
} {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const name = picture?.name ?? null;
  const version = picture?.version ?? null;
  const small = picture?.small ?? false;
  const key = picture?.key ?? null;
  const run = picture?.preview?.run ?? null;
  const index = picture?.preview?.index ?? null;
  const frame = picture?.frame;

  useEffect(() => {
    if (name === null || key === null) {
      return;
    }
    const asked: Picture = {
      name,
      version,
      small,
      preview: run !== null && index !== null ? { run, index } : null,
      ...(frame !== undefined ? { frame } : {}),
      key,
    };
    let current = true;
    entryOf(asked).promise.then(
      (url) => current && setLoaded({ picture: asked, url, error: null }),
      (cause: unknown) =>
        current &&
        setLoaded({ picture: asked, url: null, error: describe(cause) }),
    );
    return () => {
      current = false;
    };
  }, [name, version, small, key, run, index, frame]);

  if (picture === null) {
    return { url: null, error: null };
  }
  const ready = cacheOf(picture).get(picture.key)?.url ?? null;
  if (ready !== null) {
    return { url: ready, error: null };
  }
  if (
    loaded &&
    loaded.picture.small === picture.small &&
    loaded.picture.key === picture.key
  ) {
    return { url: loaded.url, error: loaded.error };
  }
  const before =
    loaded !== null &&
    loaded.picture.small === picture.small &&
    loaded.picture.name === picture.name &&
    (picture.small
      ? loaded.picture.version === picture.version &&
        loaded.picture.frame === picture.frame
      : picture.preview !== null ||
        loaded.picture.preview !== null ||
        (picture.frame !== undefined && loaded.picture.frame !== undefined));
  return { url: before ? loaded.url : null, error: null };
}
