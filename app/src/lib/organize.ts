import { useSyncExternalStore } from "react";

import {
  copyImage,
  createFolder,
  deleteFolder,
  deleteImage,
  holdCalls,
  importImage,
  moveFolder,
  moveImage,
} from "@/lib/api";
import type { Dropped } from "@/lib/drops";
import { AppError, describe } from "@/lib/errors";
import { changeQueue, type Change, type Failure } from "@/lib/operations";
import {
  folderOf,
  freeName,
  joined,
  movedPath,
  splitName,
  within,
} from "@/lib/paths";
import { gone, renamed } from "@/lib/renames";
import { newUploadId, thumbOf, uploadFile } from "@/lib/uploads";

// The extensions an image is kept under as its file has it, as `KEPT_AS_IS` in the library. Any other comes in as a PNG.
const KEPT = new Set([".png", ".jpg", ".webp", ".gif", ".svg"]);
// What a folder brought in is searched for. The server reads more, by content, from a file brought in by itself.
const IMAGE = /\.(png|jpe?g|webp|gif|svg|bmp|tiff?)$/i;
const PREVIEWS_KEPT = 300;

// The files being brought in, each by the upload it goes up as, a small copy of each to show until it is listed, and
// the name each had where it came from.
const files = new Map<string, File>();
const previews = new Map<string, string>();
const names = new Map<string, string>();
const watchers = new Set<() => void>();
let previewing: Promise<unknown> = Promise.resolve();

async function bring(upload: string, folder: string): Promise<string> {
  const file = files.get(upload);
  if (!file) {
    throw new AppError("That file is no longer held. Add it again.");
  }
  try {
    await uploadFile(
      upload,
      file.name,
      new Uint8Array(await file.arrayBuffer()),
    );
    return (await importImage(upload, folder || null, true)).name;
  } finally {
    files.delete(upload);
  }
}

/**
 * The changes the person makes to the images and folders of the directory. A name that is taken becomes the next
 * free one like it, as a file manager does when it keeps both.
 */
export const changes = changeQueue({
  run: async (change) => {
    switch (change.kind) {
      case "folder":
        return createFolder(change.path, true);
      case "move":
        return change.folder
          ? moveFolder(change.from, change.to, true)
          : (await moveImage(change.from, change.to, true)).name;
      case "copy":
        return (await copyImage(change.from, change.to, true)).name;
      case "add":
        return bring(change.source, folderOf(change.path));
      case "delete":
        if (!change.folder) {
          await deleteImage(change.path);
          gone(change.path);
        } else if ((await deleteFolder(change.path)).length > 0) {
          throw new AppError(
            "Its images were deleted. The other files in it were left.",
          );
        }
        return change.path;
    }
  },
  onMoved: renamed,
  describe,
});

function make(change: Change) {
  changes.add(change);
  // Until it is made, the view names things by where they are about to be.
  holdCalls(changes.idle());
}

/** Rename an image or a folder, or move it to another folder. It shows at once, and goes back if it is refused. */
export function move(from: string, to: string, folder: boolean) {
  make({ kind: "move", from, to, folder });
}

/** Make a folder, which shows at once. */
export function makeFolder(path: string) {
  make({ kind: "folder", path });
}

/**
 * Copy an image, or a folder with what is in it of `folders` and `images`, which are every folder and image there
 * is. A copied folder is made here, folder by folder and image by image.
 */
export function copy(
  from: string,
  to: string,
  folder: boolean,
  folders: string[],
  images: string[],
) {
  if (!folder) {
    make({ kind: "copy", from, to });
    return;
  }
  makeFolder(to);
  // Sorted, so each folder is made before the ones in it.
  for (const each of folders.filter((each) => each !== from).sort()) {
    if (within(each, from)) {
      makeFolder(movedPath(each, from, to));
    }
  }
  for (const each of images) {
    if (within(each, from)) {
      make({ kind: "copy", from: each, to: movedPath(each, from, to) });
    }
  }
}

/** Delete an image, or a folder with the images in it. It goes at once, and comes back if it could not be deleted. */
export function remove(path: string, folder: boolean) {
  make({ kind: "delete", path, folder });
}

/** The name a file comes in under, by its extension. The server goes by its content, and its answer is what stays. */
function comesInAs(name: string): string {
  const [stem, extension] = splitName(name);
  const lower = extension.toLowerCase();
  return stem + (KEPT.has(lower) ? lower : lower === ".jpeg" ? ".jpg" : ".png");
}

function preview(upload: string, file: File) {
  // One at a time, since each reads its whole image.
  previewing = previewing
    .then(() => thumbOf(file))
    .then((url) => {
      if (url === null) {
        return;
      }
      previews.set(upload, url);
      for (const old of previews.keys()) {
        if (previews.size <= PREVIEWS_KEPT) {
          break;
        }
        previews.delete(old);
        names.delete(old);
      }
      for (const watcher of watchers) {
        watcher();
      }
    });
}

/**
 * Bring files and folders from outside into `folder`, each as a new image that shows at once and is there for real
 * once it has gone up. A folder comes in with the folders in it, and of its files only the images. `taken` says
 * whether a path is in use, whatever its case.
 */
export function bringIn(
  dropped: Dropped,
  folder: string,
  taken: (path: string) => boolean,
) {
  const used = new Set<string>();
  const free = (path: string, isFolder: boolean) => {
    const name = freeName(
      path,
      isFolder,
      (each) => taken(each) || used.has(each.toLowerCase()),
    );
    used.add(name.toLowerCase());
    return name;
  };
  // Where each folder dropped goes, which has a number when its name is taken.
  const tops = new Map<string, string>();
  const placed = (path: string) => {
    const top = path.split("/")[0];
    let to = tops.get(top);
    if (to === undefined) {
      to = free(joined(folder, top), true);
      tops.set(top, to);
    }
    return movedPath(path, top, to);
  };
  for (const each of dropped.folders) {
    makeFolder(placed(each));
  }
  for (const { path, file } of dropped.files) {
    const inside = path.includes("/");
    if (inside && !file.type.startsWith("image/") && !IMAGE.test(file.name)) {
      continue;
    }
    const upload = newUploadId();
    files.set(upload, file);
    names.set(upload, file.name);
    make({
      kind: "add",
      path: free(
        joined(inside ? placed(folderOf(path)) : folder, comesInAs(file.name)),
        false,
      ),
      source: upload,
    });
    preview(upload, file);
  }
}

/** The name a file brought in had where it came from, by its upload, which is not always the name it shows under. */
export function broughtName(upload: string): string | null {
  return names.get(upload) ?? null;
}

/** A small copy of a file being brought in, by its upload, once one is made; null for a file no browser can draw. */
export function usePreview(upload: string): string | null {
  return useSyncExternalStore(
    (watcher) => {
      watchers.add(watcher);
      return () => {
        watchers.delete(watcher);
      };
    },
    () => previews.get(upload) ?? null,
  );
}

/** The changes that could not be made, until a later one is made or they are dismissed. */
export function useFailures(): Failure[] {
  return useSyncExternalStore(changes.subscribe, changes.failures);
}

export const dismissFailures = changes.dismiss;

/** Tell of something that could not be done outside these changes, with the ones that failed: what, and why. */
export const reportFailure = changes.report;
