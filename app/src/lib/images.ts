import { useEffect, useSyncExternalStore } from "react";

import {
  listImages,
  showImage,
  type ImageListing,
  type ImageSummary,
} from "@/lib/api";
import { describe } from "@/lib/errors";
import { pathAfter, type Change } from "@/lib/operations";
import { changes } from "@/lib/organize";
import { movedPath, within } from "@/lib/paths";
import { poll } from "@/lib/poll";
import { gone, onRenamed, rekey, renamed } from "@/lib/renames";

/** An image the server was asked to bring up, as `open_app` from the host session does, in the directory it is in. */
export type Brought = { name: string; dataDirectory: string };

type Images = {
  listing: ImageListing | null;
  error: string | null;
  /** The image the server was last asked to bring up from anywhere but here; a new object each time it is asked. */
  brought: Brought | null;
};

const listeners = new Set<() => void>();
// The listing as the server gave it, and what `changes` knows it by.
let read: { listing: ImageListing; asked: number } | null = null;
let brought: Brought | null = null;
let error: string | null = null;
// The image the app shows as the server last had it; undefined before the first listing.
let followed: string | null | undefined = undefined;
// Counts the picks made here as each starts and as it is recorded. A listing asked for across one may still have the
// image shown before it, so it does not move the view.
let picks = 0;
let state: Images = { listing: null, error: null, brought: null };
const NOTHING_ARRIVING: ReadonlyMap<string, string> = new Map();
// The images that show while their files are still going up, each with the upload it goes up as.
let arriving = NOTHING_ARRIVING;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function separatorOf(directory: string): string {
  return directory.includes("\\") ? "\\" : "/";
}

/** The path of the image or folder named `name` on the machine the app runs on, as the listing gives an image's. */
function pathIn(directory: string, name: string): string {
  const separator = separatorOf(directory);
  return (
    directory.replace(/[\\/]+$/, "") +
    separator +
    name.replaceAll("/", separator)
  );
}

type Shown = {
  listing: ImageListing;
  /** The images in it that are still going up, each by its name with the upload it goes up as. */
  arriving: ReadonlyMap<string, string>;
};

/**
 * The listing with changes the server has not made yet, so they show at once. A listing may already have a change it
 * is given, so applying one twice leaves it as once.
 */
function applied(listing: ImageListing, waiting: Change[]): Shown {
  if (waiting.length === 0) {
    return { listing, arriving: NOTHING_ARRIVING };
  }
  let images = listing.images;
  let folders = listing.folders;
  const coming = new Map<string, string>();
  const at = (image: ImageSummary, name: string): ImageSummary => ({
    ...image,
    name,
    path: pathIn(listing.directory, name),
  });
  for (const change of waiting) {
    switch (change.kind) {
      case "move": {
        const after = (path: string) => movedPath(path, change.from, change.to);
        images = images.map((image) =>
          after(image.name) === image.name
            ? image
            : at(image, after(image.name)),
        );
        folders = folders.map(after);
        rekey(coming, after);
        break;
      }
      case "folder":
        folders = [...folders, change.path];
        break;
      case "copy": {
        const source = images.find((image) => image.name === change.from);
        if (source && !images.some((image) => image.name === change.to)) {
          // It shows as what it is a copy of, which it is until something is asked of it.
          images = [
            ...images,
            {
              ...at(source, change.to),
              id: null,
              status: null,
              last_run: null,
            },
          ];
        }
        break;
      }
      case "add":
        if (!images.some((image) => image.name === change.path)) {
          images = [
            ...images,
            {
              name: change.path,
              id: null,
              path: pathIn(listing.directory, change.path),
              width: null,
              height: null,
              frames: null,
              modified: null,
              sha256: null,
              current: null,
              versions: [],
              status: null,
              last_run: null,
            },
          ];
          coming.set(change.path, change.source);
        }
        break;
      case "delete":
        images = images.filter((image) =>
          change.folder
            ? !within(image.name, change.path)
            : image.name !== change.path,
        );
        if (change.folder) {
          folders = folders.filter((folder) => !within(folder, change.path));
        }
        break;
    }
  }
  return {
    listing: { ...listing, images, folders: [...new Set(folders)] },
    arriving: coming,
  };
}

function show(shown: Shown | null) {
  const listing = shown?.listing ?? null;
  if (shown !== null) {
    arriving = shown.arriving;
  }
  state = { listing, error, brought };
  for (const listener of listeners) {
    listener();
  }
}

/** Show what shows again, after something other than the listing changed. */
function reshow() {
  show(read && applied(read.listing, changes.over(read.asked)));
}

// A change shows as it is added, and stops being applied once the server has made it.
changes.subscribe(reshow);
// Once every change is made, what the server has is what shows, so it is read without waiting for the next poll.
changes.onDrained(() => void refresh());

onRenamed((from, to) => {
  if (followed) {
    followed = movedPath(followed, from, to);
  }
  reshow();
});

/**
 * Say of each image that is no longer there, going by what the server listed before and lists now, so that what the
 * view shows ahead of the server is not taken for it.
 */
function followGone(
  before: ImageListing,
  after: ImageListing,
  waiting: Change[],
) {
  const ids = new Set(after.images.map((image) => image.id));
  const names = new Set(after.images.map((image) => image.name));
  for (const image of before.images) {
    if (image.id === null ? !names.has(image.name) : !ids.has(image.id)) {
      gone(pathAfter(image.name, waiting));
    }
  }
}

/**
 * Say of each image that has another name than it showed under, by the id it keeps through a move. A relink, and a
 * move made outside the view, reach it only as a listing, so this is where everything kept by the name follows.
 */
function followMoved(before: ImageListing, after: ImageListing) {
  const names = new Map(before.images.map((image) => [image.id, image.name]));
  for (const image of after.images) {
    const was = image.id === null ? undefined : names.get(image.id);
    if (was !== undefined && was !== image.name) {
      renamed(was, image.name);
    }
  }
}

/** List the images now rather than at the next poll, as after a change made here. */
async function refresh(): Promise<void> {
  const across = picks;
  const asked = changes.asking();
  try {
    const fresh = await listImages();
    // One asked for before the listing that shows, and answered after it.
    if (read !== null && asked < read.asked) {
      return;
    }
    const waiting = changes.over(asked);
    const next = applied(fresh, waiting);
    if (state.listing !== null) {
      followMoved(state.listing, next.listing);
    }
    // Not across a change of directory, where every image is another one.
    if (read !== null && read.listing.data_directory === fresh.data_directory) {
      followGone(read.listing, fresh, waiting);
    }
    const shown = fresh.shown === null ? null : pathAfter(fresh.shown, waiting);
    if (across === picks && shown !== followed) {
      followed = shown;
      if (shown !== null) {
        brought = { name: shown, dataDirectory: fresh.data_directory };
      }
    }
    read = { listing: fresh, asked };
    changes.seen(asked);
    error = null;
    show(next);
  } catch (cause) {
    error = `Could not list the images. ${describe(cause)}`;
    reshow();
  }
}

/** Record the image as the one the app shows, which it opens on, once it is in view here. */
export function recordShown(name: string) {
  picks += 1;
  showImage(name)
    .then(
      () => {
        followed = name;
      },
      () => {
        // It stays in view here; only the record of what the app shows is behind.
      },
    )
    .finally(() => {
      picks += 1;
    });
}

/**
 * The images in the app's directory, polled, and the one the server was last asked to bring up. Call it in one place,
 * since each call polls.
 *
 * An image is brought up when the server is asked to from anywhere but here, as `open_app` from the host session
 * does, and with the first listing of a directory when the app showed one there before. An image made or changed
 * anywhere else is never brought up.
 */
export function useImages(): Images & { refresh: () => Promise<void> } {
  useEffect(() => poll(refresh), []);
  const images = useSyncExternalStore(subscribe, () => state);
  return { ...images, refresh };
}

/** The images that show while their files are still going up, each by its name with the upload it goes up as. */
export function useArriving(): ReadonlyMap<string, string> {
  return useSyncExternalStore(subscribe, () => arriving);
}

/**
 * Where a file on the machine the app runs on is, once the image or the folder named `from` in the directory is named
 * `to`. A file that is neither that nor inside it stays where it is.
 */
export function movedFile(path: string, from: string, to: string): string {
  if (read === null) {
    return path;
  }
  const { directory } = read.listing;
  return movedPath(
    path,
    pathIn(directory, from),
    pathIn(directory, to),
    separatorOf(directory),
  );
}

/** The file of the image named `name` on the machine the app runs on; null before the directory is known. */
export function fileOf(name: string): string | null {
  return read === null ? null : pathIn(read.listing.directory, name);
}

/** A directory as the app shows it, by its last two folders, such as `desk-study\.image-design`. */
export function shortDirectory(path: string): string {
  const separator = path.includes("\\") ? "\\" : "/";
  return path.split(separator).filter(Boolean).slice(-2).join(separator);
}
