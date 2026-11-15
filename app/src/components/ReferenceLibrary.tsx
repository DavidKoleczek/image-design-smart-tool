import { useEffect, useMemo, useState } from "react";

import { ReferencePreview } from "@/components/ReferencePreview";
import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon, type IconName } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { Tooltip } from "@/components/ui/tooltip";
import {
  chooseReferenceFiles,
  chooseReferenceFolder,
  listReferenceFolder,
  readReferenceLibrary,
  type AppFolder,
  type FolderReference,
  type ImageListing,
  type ReferenceEntry,
  type ReferenceLibrary as Library,
} from "@/lib/api";
import { describe } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { baseName, folderOf, joined } from "@/lib/paths";
import {
  addEntries,
  entryOf,
  fileName,
  rememberEntries,
  toggleEntry,
  togglePin,
  versionBlock,
  versionEntry,
  type Reference,
} from "@/lib/references";
import { flushAppState, updateAppState, useAppState } from "@/lib/state";
import { folderTree, foldersOf, rowsOf } from "@/lib/tree";
import { cn } from "@/lib/utils";

const FOLDER = "folder:";
const INDENT = 16;
const NONE: ReadonlySet<string> = new Set();

/** What the library shows: one of its own lists, or a pinned folder by its path after `FOLDER`. */
type Source = string;

/** An entry with where it is in the folders its list has: its path there, with forward slashes. */
type Placed = { entry: ReferenceEntry; at: string };

function RailItem({
  icon,
  label,
  title,
  active = false,
  onClick,
  onRemove,
}: {
  icon: IconName;
  label: string;
  title?: string;
  active?: boolean;
  onClick: () => void;
  onRemove?: () => void;
}) {
  return (
    <li className="group relative">
      <button
        type="button"
        title={title}
        aria-current={active || undefined}
        onClick={onClick}
        className={cn(
          "flex h-7 w-full cursor-default items-center gap-2 rounded-sm pr-1.5 pl-2 text-left text-label outline-none hover:bg-hover focus-visible:bg-hover",
          active && "bg-accent-soft hover:bg-accent-soft",
        )}
      >
        <Icon name={icon} className="text-ink-muted" />
        <span className="min-w-0 flex-1 truncate">{label}</span>
      </button>
      {onRemove && (
        <button
          type="button"
          aria-label={`Unpin ${label}`}
          title="Unpin"
          onClick={onRemove}
          className="absolute top-1 right-1 hidden size-5 place-items-center rounded-sm text-ink-muted group-focus-within:grid group-hover:grid hover:bg-hover hover:text-ink"
        >
          <Icon name="close" />
        </button>
      )}
    </li>
  );
}

function PinButton({
  entry,
  pinned,
  className,
}: {
  entry: ReferenceEntry;
  pinned: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pinned}
      aria-label={pinned ? `Unpin ${entry.name}` : `Pin ${entry.name}`}
      title={pinned ? "Unpin" : "Pin"}
      onClick={() => togglePin(entry.path)}
      className={cn(
        "absolute grid size-5.5 place-items-center rounded-sm group-focus-within:opacity-100 group-hover:opacity-100 hover:text-ink",
        pinned ? "text-accent-ink" : "text-ink-muted opacity-0",
        className,
      )}
    >
      <Icon name={pinned ? "pinned" : "pin"} />
    </button>
  );
}

function ExpandButton({
  entry,
  onExpand,
  className,
}: {
  entry: ReferenceEntry;
  onExpand: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={`Expand ${entry.name}`}
      title="Expand"
      onClick={onExpand}
      className={cn(
        "absolute grid size-5.5 place-items-center rounded-sm text-ink-muted opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 hover:text-ink",
        className,
      )}
    >
      <Icon name="expand" />
    </button>
  );
}

type Shown = {
  entry: ReferenceEntry;
  /** What it is called where it shows: in a tree of folders, its name in its folder. */
  label: string;
  picked: boolean;
  pinned: boolean;
  /** Why it cannot be added now. */
  blocked: string | null;
  onToggle: () => void;
  onExpand: () => void;
};

function Tile({
  entry,
  label,
  picked,
  pinned,
  blocked,
  onToggle,
  onExpand,
}: Shown) {
  return (
    <li className="group relative min-w-0">
      <button
        type="button"
        aria-pressed={picked}
        aria-disabled={blocked ? true : undefined}
        title={blocked ?? undefined}
        onClick={() => !blocked && onToggle()}
        className={cn(
          "relative block aspect-square w-full cursor-default overflow-hidden rounded-sm border focus-visible:focus-ring focus-visible:outline-none",
          picked
            ? "border-accent-ink ring-1 ring-accent-ink"
            : "border-line hover:border-ink-muted",
          blocked && "opacity-45",
        )}
      >
        <ReferenceThumb
          reference={entry}
          className="size-full rounded-none border-0"
        />
        {picked && (
          <span className="absolute right-1 bottom-1 grid size-4.5 place-items-center rounded-full bg-accent text-on-accent">
            <Icon name="check" />
          </span>
        )}
      </button>
      <ExpandButton
        entry={entry}
        onExpand={onExpand}
        className="top-1 right-7.5 bg-panel/90"
      />
      <PinButton
        entry={entry}
        pinned={pinned}
        className="top-1 right-1 bg-panel/90"
      />
      <p
        title={entry.name}
        className="mt-1 truncate mono-annotation text-ink-muted"
      >
        {label}
      </p>
    </li>
  );
}

function Row({
  entry,
  label,
  picked,
  pinned,
  blocked,
  onToggle,
  onExpand,
  indent,
}: Shown & {
  /** How far in it starts, in a tree of folders. */
  indent?: number;
}) {
  return (
    <li className="group relative">
      <button
        type="button"
        aria-pressed={picked}
        aria-disabled={blocked ? true : undefined}
        title={blocked ?? undefined}
        onClick={() => !blocked && onToggle()}
        style={indent === undefined ? undefined : { paddingLeft: indent }}
        className={cn(
          "flex h-6.5 w-full cursor-default items-center gap-2 rounded-sm pr-14 pl-2 text-left whitespace-nowrap outline-none hover:bg-hover focus-visible:bg-hover",
          picked && "bg-accent-soft hover:bg-accent-soft",
          blocked && "opacity-45",
        )}
      >
        <ReferenceThumb reference={entry} className="size-4.5" />
        <span
          title={entry.name}
          className={cn("min-w-0 flex-1 truncate", picked && "font-medium")}
        >
          {label}
        </span>
        <span className="w-24 shrink-0 mono-annotation text-ink-muted">
          {entry.width !== null &&
            entry.height !== null &&
            dimensions(entry.width, entry.height)}
        </span>
        <span className="grid w-4 shrink-0 place-items-center text-accent-ink">
          {picked && <Icon name="check" />}
        </span>
      </button>
      <ExpandButton
        entry={entry}
        onExpand={onExpand}
        className="top-0.5 right-7.5"
      />
      <PinButton entry={entry} pinned={pinned} className="top-0.5 right-1" />
    </li>
  );
}

/** A folder's line in the tree, which opens and closes it, as in the list of your images. */
function FolderRow({
  path,
  depth,
  open,
  onToggle,
}: {
  path: string;
  depth: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        style={{ paddingLeft: 8 + depth * INDENT }}
        className="flex h-6.5 w-full cursor-default items-center gap-1 rounded-sm pr-2 text-left whitespace-nowrap outline-none hover:bg-hover focus-visible:bg-hover"
      >
        <Icon
          name="chevron"
          className={cn(
            "text-ink-muted transition-transform",
            !open && "-rotate-90",
          )}
        />
        <Icon name="folder" className="mr-0.5 text-ink-muted" />
        <span title={path} className="min-w-0 truncate">
          {baseName(path)}
        </span>
      </button>
    </li>
  );
}

/** What heads a folder's images in the grid, as in the grid of your images. */
function FolderHeading({ path }: { path: string }) {
  const above = folderOf(path);
  return (
    <h3 className="mb-1.5 flex h-6 items-center gap-1.5 mono-annotation whitespace-nowrap text-ink-muted">
      <Icon name="folder" />
      <span title={path} className="flex min-w-0 truncate">
        {above && <span className="truncate">{above}/</span>}
        <span className="shrink-0">{baseName(path)}</span>
      </span>
    </h3>
  );
}

/**
 * What a request can take as references, to pick with a click: what is pinned in this project, the images here and
 * their earlier versions, what requests here were given before, and pinned folders, each showing its images and those
 * in its folders, or opening the file dialog. Each can be shown large first.
 */
export function ReferenceLibrary({
  open,
  onOpenChange,
  target,
  references,
  room,
  full,
  listing,
  source,
  edited,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What the request's references are kept under. */
  target: string;
  references: Reference[];
  room: number;
  /** Why the request can take no more references, once it has all it can. */
  full: string | null;
  listing: ImageListing | null;
  /** The image the request edits, which is not offered as a reference to itself. */
  source: string | null;
  /** The version of it the request edits, by its id, which is not offered either; null for the image's file. */
  edited: string | null;
}) {
  const { state } = useAppState();
  const [showing, setShowing] = useState<Source>("pinned");
  const [asList, setAsList] = useState(false);
  const [query, setQuery] = useState("");
  const [library, setLibrary] = useState<Library | null>(null);
  const [inFolder, setInFolder] = useState<{
    path: string;
    entries: FolderReference[];
    /** Where its next page starts; null once every image is listed. */
    after: string | null;
  } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  // The folders closed in each source's list, by the source.
  const [closedIn, setClosedIn] = useState<
    ReadonlyMap<Source, ReadonlySet<string>>
  >(new Map());
  // The entry shown large, by its path.
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    let current = true;
    readReferenceLibrary().then(
      (read) => {
        rememberEntries([...read.pinned, ...read.used]);
        if (current) {
          setLibrary(read);
        }
      },
      (cause: unknown) => current && setError(describe(cause)),
    );
    return () => {
      current = false;
    };
  }, [open]);

  const opened =
    state.folders.find(
      (folder) =>
        folder.shows === "files" && showing === `${FOLDER}${folder.path}`,
    ) ?? null;
  const shows = opened || !showing.startsWith(FOLDER) ? showing : "pinned";
  const openedPath = opened?.path ?? null;

  useEffect(() => {
    if (!open || openedPath === null) {
      return;
    }
    let current = true;
    // The server lists only a folder it knows is pinned, so the pin is saved first.
    flushAppState()
      .then(() => listReferenceFolder(openedPath, null))
      .then(
        (page) => {
          rememberEntries(page.entries);
          if (current) {
            setInFolder({ path: openedPath, ...page });
          }
        },
        (cause: unknown) => {
          if (current) {
            setError(describe(cause));
            setInFolder({ path: openedPath, entries: [], after: null });
          }
        },
      );
    return () => {
      current = false;
    };
  }, [open, openedPath]);

  const loadMore = async () => {
    if (inFolder === null || inFolder.after === null) {
      return;
    }
    const { path, after } = inFolder;
    setLoadingMore(true);
    try {
      const page = await listReferenceFolder(path, after);
      rememberEntries(page.entries);
      setInFolder((before) =>
        before?.path === path && before.after === after
          ? {
              path,
              entries: [...before.entries, ...page.entries],
              after: page.after,
            }
          : before,
      );
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setLoadingMore(false);
    }
  };

  const here = useMemo(
    () =>
      (listing?.images ?? [])
        .filter((image) => image.sha256 !== null && image.name !== source)
        .map((image) => ({
          name: image.name,
          path: image.path,
          width: image.width,
          height: image.height,
        })),
    [listing, source],
  );
  // Each image's versions show under it, as a folder's images do under the folder.
  const versions = useMemo(
    () =>
      (listing?.images ?? []).flatMap((image) =>
        image.versions
          .filter(
            (version) =>
              versionBlock(
                image,
                version,
                image.name === source ? edited : null,
              ) === null,
          )
          .map((version) => ({
            entry: versionEntry(image, version),
            at: joined(image.name, version.id),
          })),
      ),
    [listing, source, edited],
  );
  // So one of them that is pinned shows under Pinned with its name in the directory and its size.
  useEffect(
    () => rememberEntries([...here, ...versions.map(({ entry }) => entry)]),
    [here, versions],
  );
  const sourcePath =
    listing?.images.find((image) => image.name === source)?.path ?? null;
  const loaded =
    inFolder !== null && inFolder.path === openedPath ? inFolder : null;
  // The images here and a pinned folder's are in folders, which show as the list of your images does.
  const placed: Placed[] | null =
    shows === "here"
      ? here.map((entry) => ({ entry, at: entry.name }))
      : shows === "versions"
        ? versions
        : openedPath !== null
          ? (loaded?.entries ?? []).map((entry) => ({
              entry,
              at: joined(entry.folder, entry.name),
            }))
          : null;
  const items = (
    placed?.map(({ entry }) => entry) ??
    (shows === "pinned" ? state.pins.map(entryOf) : (library?.used ?? []))
  ).filter((entry) => entry.path !== sourcePath);
  const needle = query.trim().toLowerCase();
  // In folders, a search finds what is in a folder of that name too, as in the list of your images.
  const shownPlaced = (placed ?? [])
    .filter(({ entry }) => entry.path !== sourcePath)
    .filter(({ at }) => !needle || at.toLowerCase().includes(needle));
  const shown = placed
    ? shownPlaced.map(({ entry }) => entry)
    : needle
      ? items.filter((entry) => entry.name.toLowerCase().includes(needle))
      : items;
  const title =
    shows === "pinned"
      ? "Pinned"
      : shows === "here"
        ? "Images here"
        : shows === "versions"
          ? "Earlier versions"
          : shows === "used"
            ? "Used before"
            : fileName(openedPath ?? "");
  const more = loaded?.after ?? null;
  const empty =
    openedPath !== null && loaded === null
      ? null
      : needle && items.length > 0
        ? `Nothing ${more === null ? "" : "listed so far "}in ${title} matches ${query.trim()}.`
        : shows === "pinned"
          ? "Nothing pinned yet."
          : shows === "here"
            ? "No other images here."
            : shows === "versions"
              ? "No earlier versions here."
              : shows === "used"
                ? "Nothing used here yet."
                : more === null
                  ? `${title} has no images.`
                  : `No images in ${title} so far.`;

  const tree = placed
    ? folderTree(shownPlaced.map(({ at }) => ({ path: at, folder: false })))
    : null;
  const byAt = new Map(shownPlaced.map(({ entry, at }) => [at, entry]));
  const closed = needle ? NONE : (closedIn.get(shows) ?? NONE);
  const rows = tree ? rowsOf(tree, closed) : [];
  const groups = tree
    ? foldersOf(tree).filter((folder) => folder.files.length > 0)
    : [];
  // What the arrows step through once one is shown large: the files in the order they show.
  const order = !tree
    ? shown
    : (asList
        ? rows.filter((row) => !row.folder).map((row) => row.path)
        : groups.flatMap((folder) => folder.files)
      ).flatMap((at) => byAt.get(at) ?? []);
  const nested = tree !== null && tree.folders.length > 0;
  const toggleFolder = (path: string) =>
    setClosedIn((before) => {
      const folders = new Set(before.get(shows));
      if (!folders.delete(path)) {
        folders.add(path);
      }
      return new Map(before).set(shows, folders);
    });

  const picked = new Set(references.map((reference) => reference.path));
  const blockedOf = (entry: ReferenceEntry) =>
    !picked.has(entry.path) && full ? full : null;
  const toggle = (entry: ReferenceEntry) => toggleEntry(target, entry, room);
  const entryProps = (entry: ReferenceEntry, at?: string): Shown => ({
    entry,
    label: at === undefined ? entry.name : baseName(at),
    picked: picked.has(entry.path),
    pinned: state.pins.includes(entry.path),
    blocked: blockedOf(entry),
    onToggle: () => toggle(entry),
    onExpand: () => setExpanded(entry.path),
  });

  const choose = async (folder: string | null) => {
    setError(null);
    try {
      const chosen = await chooseReferenceFiles(folder);
      rememberEntries(chosen);
      addEntries(target, chosen, room);
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const pinFolder = async (kind: AppFolder["shows"]) => {
    setError(null);
    try {
      const path = await chooseReferenceFolder();
      if (path === null) {
        return;
      }
      updateAppState((current) => ({
        ...current,
        folders: [
          ...current.folders.filter((folder) => folder.path !== path),
          { path, shows: kind },
        ],
      }));
      if (kind === "files") {
        setShowing(`${FOLDER}${path}`);
      }
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const unpinFolder = (path: string) =>
    updateAppState((current) => ({
      ...current,
      folders: current.folders.filter((folder) => folder.path !== path),
    }));

  const tiles = (list: { entry: ReferenceEntry; at?: string }[]) => (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-2.5">
      {list.map(({ entry, at }) => (
        <Tile key={entry.path} {...entryProps(entry, at)} />
      ))}
    </ul>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="References" className="sm:max-w-240">
        <div className="flex h-[min(56rem,calc(100dvh-7.5rem))] min-h-0 max-sm:h-auto max-sm:flex-1">
          <nav
            aria-label="Library"
            className="flex w-44 shrink-0 flex-col overflow-y-auto border-r border-line p-1"
          >
            <ul className="flex flex-col gap-px">
              <RailItem
                icon="pinned"
                label="Pinned"
                active={shows === "pinned"}
                onClick={() => setShowing("pinned")}
              />
              <RailItem
                icon="image"
                label="Images here"
                active={shows === "here"}
                onClick={() => setShowing("here")}
              />
              <RailItem
                icon="clock"
                label="Used before"
                active={shows === "used"}
                onClick={() => setShowing("used")}
              />
              <RailItem
                icon="copy"
                label="Earlier versions"
                active={shows === "versions"}
                onClick={() => setShowing("versions")}
              />
            </ul>
            <div className="mt-2 flex items-center justify-between pl-2 text-caption font-medium text-ink-muted">
              Folders
              <Menu>
                <Tooltip content="Pin a folder">
                  <MenuTrigger
                    render={<Button size="sm" icon aria-label="Pin a folder" />}
                  >
                    <Icon name="add" />
                  </MenuTrigger>
                </Tooltip>
                <MenuContent>
                  <MenuItem onClick={() => void pinFolder("files")}>
                    <Icon name="folder" />
                    Folder to browse here...
                  </MenuItem>
                  <MenuItem onClick={() => void pinFolder("dialog")}>
                    <Icon name="file" />
                    Folder to choose files from...
                  </MenuItem>
                </MenuContent>
              </Menu>
            </div>
            <ul className="flex flex-col gap-px">
              {state.folders.map((folder) => (
                <RailItem
                  key={folder.path}
                  icon="folder"
                  label={fileName(folder.path)}
                  title={
                    folder.shows === "dialog"
                      ? `Choose files from ${folder.path}`
                      : folder.path
                  }
                  active={shows === `${FOLDER}${folder.path}`}
                  onClick={() =>
                    folder.shows === "dialog"
                      ? void choose(folder.path)
                      : setShowing(`${FOLDER}${folder.path}`)
                  }
                  onRemove={() => unpinFolder(folder.path)}
                />
              ))}
            </ul>
            <ul className="mt-auto border-t border-line pt-1">
              <RailItem
                icon="file"
                label="Choose files..."
                onClick={() => void choose(null)}
              />
            </ul>
          </nav>
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-9 shrink-0 items-center gap-2 border-b border-line pr-1.5 pl-3">
              <span
                title={openedPath ?? undefined}
                className="min-w-0 flex-1 truncate text-label"
              >
                {title}
              </span>
              <label className="flex h-6 w-36 shrink-0 items-center gap-1.5 rounded-sm border border-line-control bg-field pr-1.5 pl-2 focus-within:border-ink focus-within:bg-panel">
                <Icon name="search" className="text-ink-muted" />
                <input
                  type="search"
                  value={query}
                  placeholder="Filter"
                  aria-label={`Filter ${title}`}
                  onChange={(event) => setQuery(event.target.value)}
                  className="min-w-0 flex-1 bg-transparent text-label font-normal outline-none placeholder:text-ink-muted [&::-webkit-search-cancel-button]:hidden"
                />
              </label>
              <Tooltip content={asList ? "Show as a grid" : "Show as files"}>
                <Button
                  size="sm"
                  icon
                  aria-label={asList ? "Show as a grid" : "Show as files"}
                  onClick={() => setAsList((list) => !list)}
                >
                  <Icon name={asList ? "grid" : "list"} />
                </Button>
              </Tooltip>
            </header>
            {error && (
              <Notice className="m-2" onDismiss={() => setError(null)}>
                {error}
              </Notice>
            )}
            <div
              className={cn(
                "min-h-0 flex-1 overflow-y-auto",
                asList ? "px-1.5 pb-2" : "p-2.5",
              )}
            >
              {empty === null ? (
                <p className="flex items-center justify-center gap-2 px-1 py-6 text-caption text-ink-muted">
                  <LoadingMark />
                  Looking for images in {title}...
                </p>
              ) : shown.length === 0 ? (
                <p className="px-1 py-6 text-center text-caption text-ink-muted">
                  {empty}
                </p>
              ) : asList ? (
                <>
                  <div
                    className={cn(
                      "flex h-7 items-center gap-2 pr-14 mono-annotation text-ink-muted",
                      nested ? "pl-6.5" : "pl-2",
                    )}
                  >
                    <span className="flex-1">Name</span>
                    <span className="w-24">Size</span>
                    <span className="w-4" />
                  </div>
                  <ul className="flex flex-col gap-px">
                    {tree
                      ? rows.map((row) => {
                          if (row.folder) {
                            return (
                              <FolderRow
                                key={row.path}
                                path={row.path}
                                depth={row.depth}
                                open={row.open}
                                onToggle={() => toggleFolder(row.path)}
                              />
                            );
                          }
                          const entry = byAt.get(row.path);
                          return (
                            entry && (
                              <Row
                                key={entry.path}
                                {...entryProps(entry, row.path)}
                                indent={
                                  nested ? 26 + row.depth * INDENT : undefined
                                }
                              />
                            )
                          );
                        })
                      : shown.map((entry) => (
                          <Row key={entry.path} {...entryProps(entry)} />
                        ))}
                  </ul>
                </>
              ) : tree ? (
                <div className="flex flex-col gap-4">
                  {groups.map((folder) => (
                    <section key={folder.path}>
                      {folder.path && <FolderHeading path={folder.path} />}
                      {tiles(
                        folder.files.flatMap((at) => {
                          const entry = byAt.get(at);
                          return entry ? [{ entry, at }] : [];
                        }),
                      )}
                    </section>
                  ))}
                </div>
              ) : (
                tiles(shown.map((entry) => ({ entry })))
              )}
              {more !== null && (
                <div className="flex items-center justify-center gap-3 py-4">
                  <span className="mono-annotation text-ink-muted">
                    {items.length} images listed
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={loadingMore}
                    onClick={() => void loadMore()}
                  >
                    {loadingMore && <LoadingMark />}
                    Load more
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
        <ReferencePreview
          entries={order}
          path={expanded}
          onShow={setExpanded}
          picked={(entry) => picked.has(entry.path)}
          blocked={blockedOf}
          onToggle={toggle}
        />
      </DialogContent>
    </Dialog>
  );
}
