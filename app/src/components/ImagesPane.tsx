import { useEffect, useState, type RefObject } from "react";

import { Explorer, type Drawing } from "@/components/explorer/Explorer";
import { useExplorer } from "@/components/explorer/useExplorer";
import { ReferenceItems, type ImageActions } from "@/components/ImageMenu";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Kbd } from "@/components/ui/kbd";
import { LoadingMark } from "@/components/ui/loading-mark";
import { MenuItem, MenuSeparator } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { Thumb } from "@/components/ui/thumb";
import { Tooltip } from "@/components/ui/tooltip";
import {
  chooseImageFiles,
  relinkImage,
  restoreImageVersion,
  showInFileManager,
  type ImageListing,
  type ImageSummary,
} from "@/lib/api";
import { AppError, describe } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { fileManager, pathIn, shortDirectory, useArriving } from "@/lib/images";
import type { Change } from "@/lib/operations";
import {
  bringIn,
  broughtName,
  copy,
  dismissFailures,
  makeFolder,
  move,
  reportFailure,
  useFailures,
  usePreview,
} from "@/lib/organize";
import { baseName, folderOf, topmost, within } from "@/lib/paths";
import { filePicture } from "@/lib/pictures";
import { onRenamed } from "@/lib/renames";
import { updateSettings, useSettings } from "@/lib/settings";
import { appStateNow, updateAppState, useAppState } from "@/lib/state";
import { failed } from "@/lib/status";
import { ago, useElapsed } from "@/lib/time";
import { matching, type Entry } from "@/lib/tree";
import { cn, copyText } from "@/lib/utils";

// The detail columns, each showing once the pane is wide enough to leave the name room.
const COLUMNS = {
  size: "hidden w-20 shrink-0 text-right @[240px]:block",
  saved: "hidden w-8 shrink-0 text-right @[330px]:block",
  changed: "hidden w-26 shrink-0 text-right @[430px]:block",
};
const NONE: ReadonlySet<string> = new Set();

/** Whether the image had a file that is no longer where the tool keeps it. */
function fileGone(image: ImageSummary): boolean {
  return (
    image.id !== null &&
    image.sha256 === null &&
    image.status !== "running" &&
    image.versions.length > 0
  );
}

function Elapsed({ since }: { since: string }) {
  return (
    <span className="mono-annotation text-ink-muted">{useElapsed(since)}</span>
  );
}

/** How an image stands, when it is not as it should be: its last request failed, or its file is gone. */
function Trouble({ image }: { image: ImageSummary }) {
  if (fileGone(image)) {
    return <Icon name="warning" label="File gone" className="text-danger" />;
  }
  return image.status !== null && failed(image.status) ? (
    <Icon name="warning" label="Failed" className="text-danger" />
  ) : null;
}

/** What follows an image's name in its line: how it stands, then its details as the pane widens. */
function Details({ image }: { image: ImageSummary }) {
  return (
    <>
      <Trouble image={image} />
      {image.status === "running" && image.last_run ? (
        <span className="flex shrink-0 items-center gap-1.5">
          <LoadingMark />
          <Elapsed since={image.last_run.started} />
        </span>
      ) : (
        <span className="contents mono-annotation text-ink-muted">
          <span className={COLUMNS.size}>
            {image.width !== null &&
              image.height !== null &&
              dimensions(image.width, image.height)}
          </span>
          <span className={COLUMNS.saved}>{image.current}</span>
          <span className={COLUMNS.changed}>
            {image.modified && ago(image.modified)}
          </span>
        </span>
      )}
    </>
  );
}

/** A file on its way in, as the small copy made of it here, until the image it becomes is listed. */
function Arriving({
  upload,
  className,
}: {
  upload: string;
  className?: string;
}) {
  const url = usePreview(upload);
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center overflow-hidden rounded-sm border border-line bg-field",
        className,
      )}
    >
      {url && (
        <img
          src={url}
          alt=""
          draggable={false}
          className="size-full object-cover opacity-60"
        />
      )}
    </span>
  );
}

/** What was not done, for the notice about a change that could not be made. */
function refused(change: Change): string {
  switch (change.kind) {
    case "folder":
      return `${baseName(change.path)} was not made.`;
    case "move":
      return folderOf(change.from) === folderOf(change.to)
        ? `${baseName(change.from)} was not renamed.`
        : `${baseName(change.from)} was not moved.`;
    case "copy":
      return `${baseName(change.from)} was not copied.`;
    case "add":
      return `${broughtName(change.source) ?? baseName(change.path)} was not added.`;
    case "delete":
      return `${baseName(change.path)} was not deleted.`;
  }
}

/**
 * The pane on the left: the images and folders of the app's directory as a file manager shows them, over the
 * directory they are kept in.
 */
export function ImagesPane({
  listing,
  current,
  creating,
  search,
  hereRef,
  onNew,
  onSelect,
  onOpenTab,
  onRemove,
  onChanged,
  ...references
}: Omit<ImageActions, "onDelete"> & {
  listing: ImageListing | null;
  /** The name of the image in view; none while a new image is being described. */
  current: string | null;
  /** The folder of the new image being described, which shows last in that folder; null while none is. */
  creating: string | null;
  /** The search field, so a key can put focus in it. */
  search: RefObject<HTMLInputElement | null>;
  /** Kept up to date with the folder the selection is in, where a new image goes; null while none is selected. */
  hereRef: RefObject<string | null>;
  /** Start a new image in the folder, or by default where a new image goes. */
  onNew: (folder?: string) => void;
  onSelect: (name: string) => void;
  /** Delete was asked for, of these images and folders, none of them inside another. */
  onRemove: (entries: Entry[]) => void;
  /** The server was asked for something that changes what it lists. */
  onChanged: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const { settings } = useSettings();
  const { state } = useAppState();
  const failures = useFailures();
  const arriving = useArriving();
  const grid = settings.images_view === "grid";
  const searching = query.trim() !== "";
  const images = new Map(
    (listing?.images ?? []).map((image) => [image.name, image]),
  );
  const folders = listing?.folders ?? [];
  const entries: Entry[] = [
    ...folders.map((path) => ({ path, folder: true })),
    ...[...images.keys()].map((path) => ({ path, folder: false })),
  ];
  const found = matching(entries, query);
  // An image a request is working on, or one still on its way in, stays where it is until that ends.
  const fixed = new Set([
    ...[...images.values()]
      .filter((image) => image.status === "running")
      .map((image) => image.name),
    ...arriving.keys(),
  ]);

  const explorer = useExplorer({
    entries: found,
    every: entries,
    view: grid ? "grid" : "details",
    current,
    // A search opens every folder, since what it found may be in a closed one.
    closed: searching ? NONE : new Set(state.closed_folders),
    fixed,
    onOpen: onSelect,
    onOpenTab,
    onToggle: (folder, open) =>
      updateAppState((before) => ({
        ...before,
        closed_folders: before.closed_folders
          .filter((each) => each !== folder)
          .concat(open ? [] : [folder]),
      })),
    onMove: move,
    onCopy: (from, to, folder) =>
      copy(from, to, folder, folders, [...images.keys()]),
    onNewFolder: makeFolder,
    onDelete: (picked) => {
      const tops = new Set(topmost(picked.map((entry) => entry.path)));
      onRemove(picked.filter((entry) => tops.has(entry.path)));
    },
    onFiles: (dropped, folder) => {
      const taken = new Set(entries.map((entry) => entry.path.toLowerCase()));
      bringIn(dropped, folder, (path) => taken.has(path.toLowerCase()));
    },
  });
  const { follow } = explorer;
  useEffect(() => onRenamed(follow), [follow]);
  useEffect(() => {
    hereRef.current = explorer.here;
  }, [hereRef, explorer.here]);
  useEffect(
    () => () => {
      hereRef.current = null;
    },
    [hereRef],
  );
  // A new image shows in the folder it goes in, which opens to show it, as do the folders that folder is in.
  useEffect(() => {
    if (
      creating &&
      appStateNow().closed_folders.some((folder) => within(creating, folder))
    ) {
      updateAppState((before) => ({
        ...before,
        closed_folders: before.closed_folders.filter(
          (folder) => !within(creating, folder),
        ),
      }));
    }
  }, [creating]);

  /** Ask for image files in the machine's own file dialog, and bring them into the folder. */
  const addImages = (folder: string) =>
    void chooseImageFiles(folder || null)
      .then(
        ({ refused: left }) => {
          for (const each of left) {
            reportFailure(
              `${each.name} was not added.`,
              describe(new AppError(each.message, each.reason)),
            );
          }
        },
        (cause: unknown) =>
          reportFailure("No images were added.", describe(cause)),
      )
      .then(onChanged);

  /** Ask the server for something about an image by its name, and say so when it could not be done. */
  const ask = (asked: Promise<unknown>, otherwise: string) =>
    void asked
      .catch((cause: unknown) => reportFailure(otherwise, describe(cause)))
      .then(onChanged);

  const organizing = (path: string) => (
    <>
      <MenuItem
        disabled={!explorer.renames(path)}
        onClick={() => explorer.clip(true)}
      >
        <Icon name="cut" />
        Cut
      </MenuItem>
      <MenuItem
        disabled={!explorer.renames(path)}
        onClick={() => explorer.clip(false)}
      >
        <Icon name="copy" />
        Copy
      </MenuItem>
    </>
  );
  const renaming = (path: string) => (
    <MenuItem
      disabled={!explorer.renames(path)}
      onClick={() => explorer.rename(path)}
    >
      <Icon name="rename" />
      Rename
    </MenuItem>
  );
  const making = (path: string) => (
    <MenuItem onClick={() => explorer.newFolder(path)}>
      <Icon name="folder-add" />
      New folder
    </MenuItem>
  );
  const adding = (path: string) => (
    <>
      <MenuItem onClick={() => addImages(path)}>
        <Icon name="import" />
        Add images
      </MenuItem>
      <MenuItem
        disabled={!explorer.pastes}
        onClick={() => explorer.paste(path)}
      >
        <Icon name="paste" />
        Paste
      </MenuItem>
    </>
  );
  // Where an entry is on this machine: its full path to copy, and the file manager to show it in. "" is the directory.
  const locating = (paths: string[]) => {
    const directory = listing?.directory;
    if (directory === undefined) {
      return null;
    }
    const full = paths.map((path) =>
      path ? pathIn(directory, path) : directory,
    );
    const [only] = paths.length === 1 ? paths : [];
    return (
      <>
        <MenuSeparator />
        <MenuItem
          onClick={() =>
            void copyText(full.join("\n")).then(
              (copied) =>
                copied ||
                reportFailure(
                  full.length === 1
                    ? "The path was not copied."
                    : "The paths were not copied.",
                  "The app could not write to the clipboard.",
                ),
            )
          }
        >
          <Icon name="copy" />
          Copy as path
        </MenuItem>
        {only !== undefined && (
          <MenuItem
            onClick={() =>
              void showInFileManager(only || null).catch((cause: unknown) =>
                reportFailure(
                  `${only ? baseName(only) : shortDirectory(directory)} was not shown in ${fileManager(directory)}.`,
                  describe(cause),
                ),
              )
            }
          >
            <Icon name="folder" />
            Open in {fileManager(directory)}
          </MenuItem>
        )}
      </>
    );
  };
  const deleting = (
    <>
      <MenuSeparator />
      <MenuItem onClick={explorer.remove} className="text-danger">
        <Icon name="delete" />
        Delete
      </MenuItem>
    </>
  );

  const menu = (entry: Entry | null) => {
    if (entry === null) {
      return (
        <>
          <MenuItem onClick={() => onNew("")}>
            <Icon name="add" />
            New image
          </MenuItem>
          {making("")}
          {adding("")}
          {locating([""])}
        </>
      );
    }
    const { path } = entry;
    const picked = [...explorer.selection.paths];
    if (picked.length > 1) {
      // Only what can go into a request: an image with a file, other than the one the request edits.
      const referable = picked.filter((each) => {
        const image = images.get(each);
        return (
          image !== undefined &&
          image.sha256 !== null &&
          each !== references.source
        );
      });
      return (
        <>
          <MenuItem
            disabled={referable.length === 0}
            onClick={() => referable.forEach(references.onAddReference)}
          >
            <Icon name="attach" />
            Add as references
          </MenuItem>
          <MenuSeparator />
          {organizing(path)}
          {locating(picked)}
          {deleting}
        </>
      );
    }
    if (entry.folder) {
      return (
        <>
          <MenuItem onClick={() => onNew(path)}>
            <Icon name="add" />
            New image
          </MenuItem>
          {making(path)}
          {adding(path)}
          <MenuSeparator />
          {organizing(path)}
          {renaming(path)}
          {locating([path])}
          {deleting}
        </>
      );
    }
    const image = images.get(path);
    const last = image?.versions.at(-1);
    if (image && last && fileGone(image)) {
      return (
        <>
          <MenuItem
            onClick={() =>
              ask(
                restoreImageVersion(path, last.id),
                `${baseName(path)} was not put back.`,
              )
            }
          >
            <Icon name="undo" />
            Put its last version back
          </MenuItem>
          {deleting}
        </>
      );
    }
    return (
      <>
        <MenuItem onClick={() => onOpenTab(path)}>
          <Icon name="link-out" />
          Open in a new tab
        </MenuItem>
        <MenuSeparator />
        <ReferenceItems name={path} {...references} />
        <MenuSeparator />
        {organizing(path)}
        {renaming(path)}
        {making(path)}
        {locating([path])}
        {deleting}
      </>
    );
  };

  const draw: Drawing = {
    icon: (path) => {
      const upload = arriving.get(path);
      if (upload !== undefined) {
        return <Arriving upload={upload} className="size-4.5 rounded-[2px]" />;
      }
      const image = images.get(path);
      return (
        image && (
          <Thumb
            picture={filePicture(image, true)}
            className="size-4.5 rounded-[2px]"
          />
        )
      );
    },
    detail: (path) => {
      if (arriving.has(path)) {
        return <LoadingMark />;
      }
      const image = images.get(path);
      return image && <Details image={image} />;
    },
    tile: (path) => {
      const upload = arriving.get(path);
      if (upload !== undefined) {
        return <Arriving upload={upload} className="aspect-square w-full" />;
      }
      const image = images.get(path);
      return (
        image && (
          <Thumb
            picture={filePicture(image, true)}
            shape={image}
            animated={(image.frames ?? 1) > 1}
            className="aspect-square w-full"
          />
        )
      );
    },
    mark: (path) => {
      const image = images.get(path);
      return (
        <>
          {(arriving.has(path) || image?.status === "running") && (
            <LoadingMark />
          )}
          {image && <Trouble image={image} />}
        </>
      );
    },
    menu,
  };
  const toggle = grid ? "Show as details" : "Show as a grid";

  return (
    <nav
      aria-label="Your images"
      className="@container flex h-full min-w-0 flex-col bg-panel"
    >
      <header className="flex h-10 shrink-0 items-center gap-0.5 border-b border-line pr-2 pl-3">
        <h2 className="flex-1 truncate text-label">Your images</h2>
        <Tooltip content="New folder">
          <Button
            size="sm"
            icon
            aria-label="New folder"
            onClick={() => explorer.newFolder()}
          >
            <Icon name="folder-add" />
          </Button>
        </Tooltip>
        <Tooltip content={toggle}>
          <Button
            size="sm"
            icon
            aria-label={toggle}
            onClick={() =>
              updateSettings((before) => ({
                ...before,
                images_view: grid ? "details" : "grid",
              }))
            }
          >
            <Icon name={grid ? "list" : "grid"} />
          </Button>
        </Tooltip>
      </header>
      <div className="m-2 flex shrink-0 items-center gap-1.5">
        <Tooltip content="New image" keys="N">
          <Button
            variant="secondary"
            aria-label="New image"
            onClick={() => onNew()}
          >
            <Icon name="add" />
            {/* The pane can be dragged narrower than the label and the search field need. */}
            <span className="hidden @3xs:inline">New image</span>
          </Button>
        </Tooltip>
        <label className="flex h-7 min-w-0 flex-1 items-center gap-2 rounded-sm border border-line-control bg-field pr-1.5 pl-2 transition-[background-color,border-color] focus-within:border-ink focus-within:bg-panel">
          <Icon name="search" className="text-ink-muted" />
          <input
            ref={search}
            value={query}
            placeholder="Search"
            aria-label="Search images"
            spellCheck={false}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setQuery("");
                event.currentTarget.blur();
              }
            }}
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-ink-muted"
          />
          <Kbd>/</Kbd>
        </label>
      </div>
      <Explorer
        explorer={explorer}
        label="Your images"
        current={current}
        draw={draw}
        header={
          <div
            role="none"
            className="sticky top-0 z-10 mb-0.5 flex h-6 items-center gap-2 border-b border-line bg-panel pr-2 pl-6.5 mono-annotation text-ink-muted"
          >
            <span className="min-w-10 flex-1 truncate">Name</span>
            <span className={COLUMNS.size}>Size</span>
            <span className={COLUMNS.saved}>Saved</span>
            <span className={COLUMNS.changed}>Changed</span>
          </div>
        }
        pending={
          creating === null
            ? undefined
            : {
                folder: creating,
                label: "New image",
                icon: (
                  <span className="grid size-4.5 shrink-0 place-items-center rounded-[2px] border border-dashed border-line-control text-ink-muted">
                    <Icon name="add" className="size-3" />
                  </span>
                ),
                tile: (
                  <span className="grid aspect-square w-full place-items-center rounded-sm border border-dashed border-line-control text-ink-muted">
                    <Icon name="add" size={20} />
                  </span>
                ),
              }
        }
      >
        {found.length === 0 && searching && (
          <p className="px-3 py-2 text-ink-muted">
            No images match {query.trim()}.
          </p>
        )}
      </Explorer>
      {failures.length > 0 && (
        <Notice
          onDismiss={dismissFailures}
          className="m-2 max-h-32 overflow-y-auto"
        >
          {failures.map((failure, index) => (
            <p key={index}>
              <b className="font-medium text-danger">
                {"change" in failure ? refused(failure.change) : failure.what}
              </b>{" "}
              {failure.why}
            </p>
          ))}
        </Notice>
      )}
      {listing?.likely.map(({ name, new_name: likely }) => (
        <Notice key={name} tone="neutral" icon="warning" className="m-2">
          <p>
            <b className="font-medium">{name} is gone.</b> {likely} may be it.
          </p>
          <Button
            size="sm"
            variant="secondary"
            className="mt-1.5"
            onClick={() =>
              ask(relinkImage(name), `${baseName(name)} was not relinked.`)
            }
          >
            Relink
          </Button>
        </Notice>
      ))}
      {listing && listing.unreadable.length > 0 && (
        <Notice
          title="Some images could not be read."
          className="m-2 max-h-32 overflow-y-auto"
        >
          {listing.unreadable.join(" ")}
        </Notice>
      )}
      {listing && (
        <footer
          title={listing.directory}
          className="shrink-0 truncate border-t border-line px-3 py-2 mono-annotation text-ink-muted"
        >
          {shortDirectory(listing.directory)}
        </footer>
      )}
    </nav>
  );
}
