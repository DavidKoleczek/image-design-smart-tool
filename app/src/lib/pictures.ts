import { useEffect, useState } from "react";

import {
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
  image: ImageSummary,
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

type Entry = { promise: Promise<string>; url: string | null };

// Thumbnails are a few kilobytes each, so a directory's worth stays; a full image can be megabytes, so only the last
// few looked at do, enough to go back and forth between versions without reading them again.
const KEPT = { small: 600, full: 12 };
const caches = {
  small: new Map<string, Entry>(),
  full: new Map<string, Entry>(),
};

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
  const cache = picture.small ? caches.small : caches.full;
  const key = picture.key;
  const kept = cache.get(key);
  if (kept) {
    // Put back as the newest, so what is still looked at is the last to go.
    cache.delete(key);
    cache.set(key, kept);
    return kept;
  }
  const { preview } = picture;
  const read = () =>
    preview
      ? readRunPreview(picture.name, preview.run, preview.index)
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
  for (const old of cache.keys()) {
    if (cache.size <= (picture.small ? KEPT.small : KEPT.full)) {
      break;
    }
    cache.delete(old);
  }
  return entry;
}

type Loaded = { picture: Picture; url: string | null; error: string | null };

/**
 * The picture read through the host: its data URL once read, or why it could not be. Two kinds keep showing what
 * showed of the same image until the new one is read: a thumbnail, so a row does not blink each time its image
 * changes, and whatever comes before or after an in-progress image, so an image forms without going blank between.
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

  useEffect(() => {
    if (name === null || key === null) {
      return;
    }
    const asked: Picture = {
      name,
      version,
      small,
      preview: run !== null && index !== null ? { run, index } : null,
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
  }, [name, version, small, key, run, index]);

  if (picture === null) {
    return { url: null, error: null };
  }
  const cache = picture.small ? caches.small : caches.full;
  const ready = cache.get(picture.key)?.url ?? null;
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
      ? loaded.picture.version === picture.version
      : picture.preview !== null || loaded.picture.preview !== null);
  return { url: before ? loaded.url : null, error: null };
}
