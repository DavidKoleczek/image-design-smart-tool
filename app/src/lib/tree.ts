import type { ImageSummary } from "@/lib/api";

/** A folder of the directory, with the folders and images directly in it. The directory itself has the path "". */
export type Folder = {
  /** Its path in the directory, with forward slashes. */
  path: string;
  name: string;
  folders: Folder[];
  images: ImageSummary[];
};

/** An image's name without the folders it is in. */
export function baseName(name: string): string {
  return name.slice(name.lastIndexOf("/") + 1);
}

/** The folder an image is in, "" for the directory itself. */
export function folderOf(name: string): string {
  return name.slice(0, Math.max(0, name.lastIndexOf("/")));
}

/** The images whose path has `query` in it, whatever its case; all of them for an empty query. */
export function matching(
  images: ImageSummary[],
  query: string,
): ImageSummary[] {
  const wanted = query.trim().toLowerCase();
  return wanted
    ? images.filter((image) => image.name.toLowerCase().includes(wanted))
    : images;
}

/** The images as the tree of folders they are in, each folder's own folders in name order. */
export function folderTree(images: ImageSummary[]): Folder {
  const root: Folder = { path: "", name: "", folders: [], images: [] };
  const folders = new Map<string, Folder>([["", root]]);
  const folder = (path: string): Folder => {
    const known = folders.get(path);
    if (known) {
      return known;
    }
    const made = { path, name: baseName(path), folders: [], images: [] };
    folders.set(path, made);
    folder(folderOf(path)).folders.push(made);
    return made;
  };
  for (const image of images) {
    folder(folderOf(image.name)).images.push(image);
  }
  for (const each of folders.values()) {
    each.folders.sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
    );
  }
  return root;
}

/** Every folder under `folder` that has images directly in it, itself first, in the order a tree shows them. */
export function foldersWithImages(folder: Folder): Folder[] {
  return [
    ...(folder.images.length > 0 ? [folder] : []),
    ...folder.folders.flatMap(foldersWithImages),
  ];
}
