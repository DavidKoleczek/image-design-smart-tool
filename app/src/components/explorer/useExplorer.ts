import { useCallback, useState } from "react";

import type { Dropped } from "@/lib/drops";
import {
  baseName,
  copyName,
  folderOf,
  freeName,
  joined,
  movedPath,
  splitName,
  topmost,
  within,
} from "@/lib/paths";
import {
  all,
  moved,
  NOTHING,
  only,
  ranged,
  showing,
  toggled,
  type Selection,
} from "@/lib/selection";
import {
  folderTree,
  foldersOf,
  rowsOf,
  type Entry,
  type Row,
} from "@/lib/tree";

export type View = "details" | "grid";

/** The name being typed in place: an entry's new one, or that of a folder which shows before it is made. */
export type Editing = { kind: "rename" | "new"; path: string };

/** What was cut or copied, to be pasted somewhere. */
type Clip = { paths: string[]; cut: boolean };

const NEW_FOLDER = "New folder";

/**
 * A file tree as a file manager has it: what shows, what is selected, the name being typed, and what was cut or
 * copied. It changes nothing itself. What the person does is reported, and shows once the entries given have it.
 */
export function useExplorer({
  entries,
  every = entries,
  view,
  current,
  closed,
  fixed,
  onOpen,
  onToggle,
  onMove,
  onCopy,
  onNewFolder,
  onDelete,
  onFiles,
}: {
  /** The files, and the folders, which need not have a file in them. A file's folders need not be listed. */
  entries: Entry[];
  /** Everything there is, when `entries` is only some of it, so a name is known to be taken though it does not show. */
  every?: Entry[];
  view: View;
  /** The file in view, which the selection goes to when something else brings another into view. */
  current: string | null;
  /** The folders that are closed in the details view. */
  closed: ReadonlySet<string>;
  /** The files that cannot be renamed, moved, cut, or copied for now, nor a folder one of them is in. */
  fixed: ReadonlySet<string>;
  /** A file was picked alone, by a click, an arrow, or Enter. */
  onOpen: (path: string) => void;
  onToggle: (folder: string, open: boolean) => void;
  /** An entry was given another name, or put in another folder. `to` is free: a name that was taken has a number. */
  onMove: (from: string, to: string, folder: boolean) => void;
  /** An entry was copied to `to`, which is free. A folder is copied with everything in it. */
  onCopy: (from: string, to: string, folder: boolean) => void;
  onNewFolder: (path: string) => void;
  onDelete: (entries: Entry[]) => void;
  /** Files from outside were dropped on a folder, "" for the top. */
  onFiles: (dropped: Dropped, folder: string) => void;
}) {
  const [kept, setKept] = useState<Selection>(() =>
    current === null ? NOTHING : only(current),
  );
  const [followed, setFollowed] = useState(current);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [clip, setClip] = useState<Clip | null>(null);
  if (current !== followed) {
    setFollowed(current);
    if (current !== null && !kept.paths.has(current)) {
      setKept(only(current));
    }
  }

  // Stable, since whoever tells the tree of a move subscribes with it.
  const follow = useCallback((from: string, to: string) => {
    const after = (path: string) => movedPath(path, from, to);
    setKept((before) => moved(before, from, to));
    setEditing((before) => before && { ...before, path: after(before.path) });
    setClip(
      (before) => before && { ...before, paths: before.paths.map(after) },
    );
  }, []);

  const root = folderTree(
    editing?.kind === "new"
      ? [...entries, { path: editing.path, folder: true }]
      : entries,
  );
  const folders = foldersOf(root);
  const rows: Row[] =
    view === "details"
      ? rowsOf(root, closed)
      : folders.flatMap((folder) => [
          ...(folder.path === ""
            ? []
            : [{ path: folder.path, folder: true, depth: 0, open: true }]),
          ...folder.files.map((path) => ({
            path,
            folder: false,
            depth: 0,
            open: false,
          })),
        ]);
  const order = rows.map((row) => row.path);
  const byPath = new Map(rows.map((row) => [row.path, row]));
  const selection = showing(kept, order);
  // Whether each thing there is is a folder, showing or not.
  const kinds = new Map([
    ...every.map((entry) => [entry.path, entry.folder] as const),
    ...folders.map((folder) => [folder.path, true] as const),
  ]);
  const taken = new Set(
    [...kinds.keys()]
      .filter((path) => path !== editing?.path)
      .map((path) => path.toLowerCase()),
  );

  const isFixed = (path: string) =>
    [...fixed].some((file) => within(file, path));

  /** Pick a file alone, which also brings it into view. A folder is only selected. */
  const pick = (path: string) => {
    setKept(only(path));
    if (byPath.get(path)?.folder === false) {
      onOpen(path);
    }
  };

  const toggle = (path: string) => {
    const row = byPath.get(path);
    if (row?.folder && view === "details") {
      onToggle(path, !row.open);
    }
  };

  /** The folder something put on the entry lands in: a folder itself, and for a file the folder it is in. */
  const folderAt = (path: string) => (kinds.get(path) ? path : folderOf(path));

  /** The folder a new folder or a paste goes in when none is named: by the entry the keys move from, or the top. */
  const folderBy = (beside?: string) => {
    const by = beside ?? selection.lead;
    return by === null || !kinds.has(by) ? "" : folderAt(by);
  };

  /** Whether the entry would go anywhere, put into the folder. */
  const lands = (path: string, folder: string, copy: boolean) => {
    // A folder cannot go into itself, or into a folder inside it.
    if (!kinds.has(path) || (kinds.get(path) && within(folder, path))) {
      return false;
    }
    return copy || folderOf(path) !== folder;
  };

  /** What of the selection, or the entry alone when it is not in it, can be moved or copied now. */
  const movable = (path?: string) => {
    const picked =
      path === undefined || selection.paths.has(path)
        ? order.filter((each) => selection.paths.has(each))
        : [path];
    return topmost(picked).filter((each) => !isFixed(each));
  };

  /** Move the entries into the folder, or copy them there. Each takes a number where its name is taken. */
  const putInto = (paths: string[], folder: string, copy: boolean) => {
    const used = new Set(taken);
    const put: string[] = [];
    for (const path of topmost(paths)) {
      if (!lands(path, folder, copy) || isFixed(path)) {
        continue;
      }
      const isFolder = kinds.get(path) ?? false;
      const name = baseName(path);
      const to = freeName(
        joined(
          folder,
          // Beside what it is a copy of, a copy says that it is one.
          copy && folderOf(path) === folder ? copyName(name, isFolder) : name,
        ),
        isFolder,
        (each) => used.has(each.toLowerCase()),
      );
      used.add(to.toLowerCase());
      (copy ? onCopy : onMove)(path, to, isFolder);
      put.push(to);
    }
    if (put.length === 0) {
      return;
    }
    // What was put somewhere is what is selected there, so a closed folder it went into opens to show it.
    if (byPath.get(folder)?.open === false) {
      onToggle(folder, true);
    }
    setKept({ paths: new Set(put), anchor: put[0], lead: put[put.length - 1] });
  };

  return {
    view,
    /** The folders from the top down, each with the files in it, for a view that shows them as sections. */
    folders,
    /** What shows, from top to bottom. */
    rows,
    order,
    selection,
    editing,
    row: (path: string): Row | undefined => byPath.get(path),
    select: setKept,
    pick,
    toggle,
    folderAt,
    /** A click on an entry, as a file manager takes it with Ctrl or Shift held. */
    click(path: string, held: { toggle: boolean; range: boolean }) {
      if (held.range) {
        setKept(ranged(selection, order, path, held.toggle));
      } else if (held.toggle) {
        setKept(toggled(selection, path));
      } else {
        pick(path);
        toggle(path);
      }
    },
    /** Move to an entry with the keys, or with `extend` stretch the selection to it. */
    go(path: string | null, extend: boolean) {
      if (path === null) {
        return;
      }
      if (extend) {
        setKept(ranged(selection, order, path));
      } else {
        pick(path);
      }
    },
    selectAll: () => setKept(all(selection, order)),
    clear: () => setKept(NOTHING),
    /** Whether the entry can be renamed, moved, cut, or copied now. */
    renames: (path: string) => !isFixed(path),
    /** Start typing another name for an entry, in place. */
    rename(path: string) {
      if (byPath.has(path) && !isFixed(path)) {
        setEditing({ kind: "rename", path });
        if (!selection.paths.has(path)) {
          setKept(only(path));
        }
      }
    },
    /**
     * Show a new folder with its name ready to type. It goes inside `beside` when that is a folder, and beside it
     * when it is a file. Without `beside` it goes by the entry the keys move from, or at the top when there is none.
     */
    newFolder(beside?: string) {
      const parent = folderBy(beside);
      if (byPath.get(parent)?.open === false) {
        onToggle(parent, true);
      }
      const path = freeName(joined(parent, NEW_FOLDER), true, (each) =>
        taken.has(each.toLowerCase()),
      );
      setEditing({ kind: "new", path });
      setKept(only(path));
    },
    /**
     * Keep the name typed, and return the path the entry has with it. A name that is taken takes a number. An empty
     * name, or the name it has, leaves an entry as it is, and a new folder with the name it was shown under.
     */
    keep(typed: string): string | null {
      if (editing === null) {
        return null;
      }
      setEditing(null);
      const { path } = editing;
      const free = (wanted: string, folder: boolean) =>
        freeName(joined(folderOf(path), wanted), folder, (each) =>
          taken.has(each.toLowerCase()),
        );
      if (editing.kind === "new") {
        const made = free(typed.trim() || baseName(path), true);
        onNewFolder(made);
        setKept(only(made));
        return made;
      }
      const folder = byPath.get(path)?.folder ?? false;
      const [name, extension] = folder
        ? [baseName(path), ""]
        : splitName(baseName(path));
      if (typed.trim() === "" || typed.trim() === name) {
        return path;
      }
      const to = free(typed.trim() + extension, folder);
      onMove(path, to, folder);
      setKept(moved(selection, path, to));
      return to;
    },
    /** Put the old name back, or drop the new folder. */
    drop() {
      setEditing(null);
    },
    /** Delete was asked for, of everything selected. */
    remove() {
      const picked = rows.filter((row) => selection.paths.has(row.path));
      if (picked.length > 0) {
        onDelete(picked.map(({ path, folder }) => ({ path, folder })));
      }
    },
    /** What a drag that starts on the entry takes with it: the selection when the entry is in it, else the entry. */
    take: (path: string) => movable(path),
    /** Whether any of the entries would go anywhere, dropped into the folder. */
    allows: (paths: string[], folder: string, copy: boolean) =>
      paths.some((path) => lands(path, folder, copy)),
    putInto,
    /** Open the entry when it is a closed folder, as when something is held over it. */
    hold(path: string) {
      if (byPath.get(path)?.open === false && view === "details") {
        onToggle(path, true);
      }
    },
    /** Cut the selection, to be moved where it is pasted, or copy it, to be copied there. */
    clip(cut: boolean) {
      const paths = movable();
      if (paths.length > 0) {
        setClip({ paths, cut });
      }
    },
    /** Whether the entry was cut, or is in a folder that was, and waits to be pasted. */
    isCut: (path: string) =>
      clip !== null &&
      clip.cut &&
      clip.paths.some((each) => within(path, each)),
    /** Forget what was cut. Says whether anything was. */
    uncut() {
      if (clip?.cut) {
        setClip(null);
        return true;
      }
      return false;
    },
    /** Whether there is something to paste. */
    pastes: clip !== null && clip.paths.some((path) => kinds.has(path)),
    /**
     * Paste what was cut or copied into the folder `beside` is or is in, or without it by the entry the keys move
     * from, or at the top. What was cut is moved, once. What was copied can be pasted again.
     */
    paste(beside?: string) {
      if (clip === null) {
        return;
      }
      putInto(clip.paths, folderBy(beside), !clip.cut);
      if (clip.cut) {
        setClip(null);
      }
    },
    /** Files from outside were dropped on the folder. */
    bring: onFiles,
    /** What was at `from` is at `to` now, so what is selected, cut, or copied, and a name being typed, stay with it. */
    follow,
  };
}

export type Explorer = ReturnType<typeof useExplorer>;
