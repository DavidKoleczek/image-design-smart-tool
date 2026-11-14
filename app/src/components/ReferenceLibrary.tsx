import { useEffect, useMemo, useState } from "react";

import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon, type IconName } from "@/components/ui/icon";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { Tooltip } from "@/components/ui/tooltip";
import {
  chooseReferenceFiles,
  chooseReferenceFolder,
  listReferenceFolder,
  readReferenceLibrary,
  type AppFolder,
  type ImageListing,
  type ReferenceEntry,
  type ReferenceLibrary as Library,
} from "@/lib/api";
import { describe } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import {
  addEntries,
  entryOf,
  fileName,
  rememberEntries,
  toggleEntry,
  togglePin,
  type Reference,
} from "@/lib/references";
import { flushAppState, updateAppState, useAppState } from "@/lib/state";
import { cn } from "@/lib/utils";

const FOLDER = "folder:";

/** What the library shows: one of its own lists, or a pinned folder by its path after `FOLDER`. */
type Source = string;

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

type Shown = {
  entry: ReferenceEntry;
  picked: boolean;
  pinned: boolean;
  /** Why it cannot be added now. */
  blocked: string | null;
  onToggle: () => void;
};

function Tile({ entry, picked, pinned, blocked, onToggle }: Shown) {
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
      <PinButton
        entry={entry}
        pinned={pinned}
        className="top-1 right-1 bg-panel/90"
      />
      <p
        title={entry.name}
        className="mt-1 truncate mono-annotation text-ink-muted"
      >
        {entry.name}
      </p>
    </li>
  );
}

function Row({ entry, picked, pinned, blocked, onToggle }: Shown) {
  return (
    <li className="group relative">
      <button
        type="button"
        aria-pressed={picked}
        aria-disabled={blocked ? true : undefined}
        title={blocked ?? undefined}
        onClick={() => !blocked && onToggle()}
        className={cn(
          "flex h-6.5 w-full cursor-default items-center gap-2 rounded-sm pr-8 pl-2 text-left whitespace-nowrap outline-none hover:bg-hover focus-visible:bg-hover",
          picked && "bg-accent-soft hover:bg-accent-soft",
          blocked && "opacity-45",
        )}
      >
        <ReferenceThumb reference={entry} className="size-4.5" />
        <span
          className={cn("min-w-0 flex-1 truncate", picked && "font-medium")}
        >
          {entry.name}
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
      <PinButton entry={entry} pinned={pinned} className="top-0.5 right-1" />
    </li>
  );
}

/**
 * What a request can take as references, to pick with a click: what is pinned in this project, the images here, what
 * requests here were given before, and pinned folders, each showing its images or opening the file dialog.
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
}) {
  const { state } = useAppState();
  const [showing, setShowing] = useState<Source>("pinned");
  const [asList, setAsList] = useState(false);
  const [query, setQuery] = useState("");
  const [library, setLibrary] = useState<Library | null>(null);
  const [inFolder, setInFolder] = useState<{
    path: string;
    entries: ReferenceEntry[];
  } | null>(null);
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
      .then(() => listReferenceFolder(openedPath))
      .then(
        (entries) => {
          rememberEntries(entries);
          if (current) {
            setInFolder({ path: openedPath, entries });
          }
        },
        (cause: unknown) => current && setError(describe(cause)),
      );
    return () => {
      current = false;
    };
  }, [open, openedPath]);

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
  // So one of them that is pinned shows under Pinned with its name in the directory and its size.
  useEffect(() => rememberEntries(here), [here]);
  const sourcePath =
    listing?.images.find((image) => image.name === source)?.path ?? null;
  const items = (
    shows === "pinned"
      ? state.pins.map(entryOf)
      : shows === "here"
        ? here
        : shows === "used"
          ? (library?.used ?? [])
          : inFolder?.path === openedPath
            ? inFolder.entries
            : []
  ).filter((entry) => entry.path !== sourcePath);
  const needle = query.trim().toLowerCase();
  const shown = needle
    ? items.filter((entry) => entry.name.toLowerCase().includes(needle))
    : items;
  const title =
    shows === "pinned"
      ? "Pinned"
      : shows === "here"
        ? "Images here"
        : shows === "used"
          ? "Used before"
          : fileName(openedPath ?? "");
  const empty =
    needle && items.length > 0
      ? `Nothing in ${title} matches ${query.trim()}.`
      : shows === "pinned"
        ? "Nothing pinned yet."
        : shows === "here"
          ? "No other images here."
          : shows === "used"
            ? "Nothing used here yet."
            : `${title} has no images.`;
  const picked = new Set(references.map((reference) => reference.path));
  const entryProps = (entry: ReferenceEntry): Shown => ({
    entry,
    picked: picked.has(entry.path),
    pinned: state.pins.includes(entry.path),
    blocked: !picked.has(entry.path) && full ? full : null,
    onToggle: () => toggleEntry(target, entry, room),
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="References" className="sm:max-w-180">
        <div className="flex h-[min(460px,70vh)] min-h-0 max-sm:h-auto max-sm:flex-1">
          <nav
            aria-label="Library"
            className="flex w-41 shrink-0 flex-col overflow-y-auto border-r border-line p-1"
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
              {shown.length === 0 ? (
                <p className="px-1 py-6 text-center text-caption text-ink-muted">
                  {empty}
                </p>
              ) : asList ? (
                <>
                  <div className="flex h-7 items-center gap-2 pr-8 pl-2 mono-annotation text-ink-muted">
                    <span className="flex-1">Name</span>
                    <span className="w-24">Size</span>
                    <span className="w-4" />
                  </div>
                  <ul className="flex flex-col gap-px">
                    {shown.map((entry) => (
                      <Row key={entry.path} {...entryProps(entry)} />
                    ))}
                  </ul>
                </>
              ) : (
                <ul className="grid grid-cols-[repeat(auto-fill,minmax(84px,1fr))] gap-2">
                  {shown.map((entry) => (
                    <Tile key={entry.path} {...entryProps(entry)} />
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
