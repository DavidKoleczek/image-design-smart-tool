import { useEffect, useState } from "react";

import {
  readImagePicture,
  type ImageSummary,
  type ImageVersion,
} from "@/lib/api";
import { describe } from "@/lib/errors";

/** What of an image to show. */
export type Picture = {
  name: string;
  /** The version kept for the image; null for its file. */
  version: string | null;
  /** A thumbnail rather than the image itself. */
  small: boolean;
  /** The hash of what is there, so the same content is read once however it is reached. */
  sha256: string;
};

/** The image's file; nothing when it has none the tool can read. */
export function filePicture(
  image: ImageSummary,
  small = false,
): Picture | null {
  return image.width === null || image.sha256 === null
    ? null
    : { name: image.name, version: null, small, sha256: image.sha256 };
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
    sha256: version.sha256,
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
  const key = picture.sha256;
  const kept = cache.get(key);
  if (kept) {
    // Put back as the newest, so what is still looked at is the last to go.
    cache.delete(key);
    cache.set(key, kept);
    return kept;
  }
  const read = () =>
    readImagePicture(picture.name, picture.version, picture.small);
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
 * The picture read through the host: its data URL once read, or why it could not be. A thumbnail keeps showing what
 * it showed of the same image until the new one is read, so a row does not blink each time its image changes.
 */
export function usePicture(picture: Picture | null): {
  url: string | null;
  error: string | null;
} {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const name = picture?.name ?? null;
  const version = picture?.version ?? null;
  const small = picture?.small ?? false;
  const sha256 = picture?.sha256 ?? null;

  useEffect(() => {
    if (name === null || sha256 === null) {
      return;
    }
    const asked = { name, version, small, sha256 };
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
  }, [name, version, small, sha256]);

  if (picture === null) {
    return { url: null, error: null };
  }
  const cache = picture.small ? caches.small : caches.full;
  const ready = cache.get(picture.sha256)?.url ?? null;
  if (ready !== null) {
    return { url: ready, error: null };
  }
  if (
    loaded &&
    loaded.picture.small === picture.small &&
    loaded.picture.sha256 === picture.sha256
  ) {
    return { url: loaded.url, error: loaded.error };
  }
  const before =
    loaded &&
    picture.small &&
    loaded.picture.small &&
    loaded.picture.name === picture.name &&
    loaded.picture.version === picture.version;
  return { url: before ? loaded.url : null, error: null };
}
