/**
 * What a drop from the system's file manager holds. A file is by its name. For a folder dropped, every folder and
 * file in it is by its path from the folder dropped, as in `photos/trip/beach.png`, with a folder before what is in it.
 */
export type Dropped = {
  folders: string[];
  files: { path: string; file: File }[];
};

/** Whether what is being dragged over the view is files from outside it. */
export function hasFiles(transfer: DataTransfer | null): boolean {
  return transfer?.types.includes("Files") ?? false;
}

async function walk(entry: FileSystemEntry, path: string, into: Dropped) {
  if (!entry.isDirectory) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject),
    );
    into.files.push({ path, file });
    return;
  }
  into.folders.push(path);
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // A read gives only some of a large folder, so it is read until it gives nothing.
  for (;;) {
    const some = await new Promise<FileSystemEntry[]>((resolve, reject) =>
      reader.readEntries(resolve, reject),
    );
    if (some.length === 0) {
      return;
    }
    for (const each of some) {
      await walk(each, `${path}/${each.name}`, into);
    }
  }
}

/** Everything in a drop. Call it in the drop's handler, since what was dropped can only be taken until it returns. */
export async function readDrop(transfer: DataTransfer): Promise<Dropped> {
  const taken = [...transfer.items]
    .filter((item) => item.kind === "file")
    .map((item) => ({
      // Not every frame a view runs in gives entries, and without them a folder cannot be read.
      entry:
        typeof item.webkitGetAsEntry === "function"
          ? item.webkitGetAsEntry()
          : null,
      file: item.getAsFile(),
    }));
  const dropped: Dropped = { folders: [], files: [] };
  for (const { entry, file } of taken) {
    try {
      if (entry) {
        await walk(entry, entry.name, dropped);
      } else if (file) {
        dropped.files.push({ path: file.name, file });
      }
    } catch {
      // What cannot be read is left out, and the rest still comes in.
    }
  }
  return dropped;
}
