import { baseName, byName, folderOf } from "@/lib/paths";

/** A file or a folder, by its path with forward slashes from the top of what the tree shows. */
export type Entry = { path: string; folder: boolean };

/** A folder with the folders and the files directly in it, each in name order. The top has the path "". */
export type Folder = {
  path: string;
  name: string;
  folders: Folder[];
  /** The paths of its files. */
  files: string[];
};

/** A line of the tree as it shows: an entry, how deep it is, and for a folder whether it is open. */
export type Row = Entry & { depth: number; open: boolean };

/** The files whose path has `query` in it, whatever its case; every entry for an empty query. */
export function matching(entries: Entry[], query: string): Entry[] {
  const wanted = query.trim().toLowerCase();
  return wanted
    ? entries.filter(
        (entry) => !entry.folder && entry.path.toLowerCase().includes(wanted),
      )
    : entries;
}

/** The entries as a tree. A folder that only a file's path names is in it as well. */
export function folderTree(entries: Entry[]): Folder {
  const root: Folder = { path: "", name: "", folders: [], files: [] };
  const folders = new Map<string, Folder>([["", root]]);
  const folder = (path: string): Folder => {
    const known = folders.get(path);
    if (known) {
      return known;
    }
    const made = { path, name: baseName(path), folders: [], files: [] };
    folders.set(path, made);
    folder(folderOf(path)).folders.push(made);
    return made;
  };
  for (const entry of entries) {
    if (entry.folder) {
      folder(entry.path);
    } else {
      folder(folderOf(entry.path)).files.push(entry.path);
    }
  }
  for (const each of folders.values()) {
    each.folders.sort((a, b) => byName(a.name, b.name));
    each.files.sort((a, b) => byName(baseName(a), baseName(b)));
  }
  return root;
}

/**
 * The lines of the tree from top to bottom: in each folder its folders, then its files. What is in a folder named in
 * `closed` is left out.
 */
export function rowsOf(
  folder: Folder,
  closed: ReadonlySet<string>,
  depth = 0,
): Row[] {
  return [
    ...folder.folders.flatMap((inside) => {
      const open = !closed.has(inside.path);
      return [
        { path: inside.path, folder: true, depth, open },
        ...(open ? rowsOf(inside, closed, depth + 1) : []),
      ];
    }),
    ...folder.files.map((path) => ({
      path,
      folder: false,
      depth,
      open: false,
    })),
  ];
}

/** Every folder, the top first and then each with the folders in it, in the order the tree shows them. */
export function foldersOf(folder: Folder): Folder[] {
  return [folder, ...folder.folders.flatMap(foldersOf)];
}
