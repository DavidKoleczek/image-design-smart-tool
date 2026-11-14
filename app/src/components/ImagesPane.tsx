import { useState, type ReactNode, type RefObject } from "react";

import { ImageMenu, type ImageActions } from "@/components/ImageMenu";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Kbd } from "@/components/ui/kbd";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import { Thumb } from "@/components/ui/thumb";
import { Tooltip } from "@/components/ui/tooltip";
import type { ImageListing, ImageSummary } from "@/lib/api";
import { dimensions } from "@/lib/format";
import { shortDirectory } from "@/lib/images";
import { filePicture } from "@/lib/pictures";
import { updateSettings, useSettings } from "@/lib/settings";
import { updateAppState, useAppState } from "@/lib/state";
import { failed } from "@/lib/status";
import { ago, useElapsed } from "@/lib/time";
import {
  baseName,
  foldersWithImages,
  folderTree,
  matching,
  type Folder,
} from "@/lib/tree";
import { cn } from "@/lib/utils";

// The detail columns, each showing once the pane is wide enough to leave the name room.
const COLUMNS = {
  size: "hidden w-20 shrink-0 text-right @[240px]:block",
  saved: "hidden w-8 shrink-0 text-right @[330px]:block",
  changed: "hidden w-26 shrink-0 text-right @[430px]:block",
};
const INDENT = 16;
const ROW =
  "flex h-full min-w-0 flex-1 cursor-default items-center gap-2 rounded-sm pr-2 text-left whitespace-nowrap focus-visible:focus-ring focus-visible:outline-none";

type Picking = ImageActions & {
  /** The name of the image in view; none while a new image is being described. */
  current: string | null;
  onSelect: (name: string) => void;
};

function Elapsed({ since }: { since: string }) {
  return (
    <span className="mono-annotation text-ink-muted">{useElapsed(since)}</span>
  );
}

/** One image in the tree: a small preview and its name, then its details as the pane widens. */
function FileRow({
  image,
  depth,
  current,
  onSelect,
  ...actions
}: Picking & { image: ImageSummary; depth: number }) {
  const viewed = current === image.name;
  return (
    <div
      className={cn(
        "group relative flex h-6.5 items-center rounded-sm",
        viewed ? "bg-accent-soft" : "hover:bg-hover",
      )}
    >
      <button
        type="button"
        title={image.name}
        aria-current={viewed || undefined}
        onClick={() => onSelect(image.name)}
        style={{ paddingLeft: 26 + depth * INDENT }}
        className={ROW}
      >
        <Thumb
          picture={filePicture(image, true)}
          className="size-4.5 rounded-[2px]"
        />
        <span
          className={cn("min-w-10 flex-1 truncate", viewed && "font-medium")}
        >
          {baseName(image.name)}
        </span>
        {image.status !== null && failed(image.status) && (
          <Icon name="warning" label="Failed" className="text-danger" />
        )}
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
      </button>
      <ImageMenu
        name={image.name}
        className={cn(
          "absolute top-1/2 right-1 -translate-y-1/2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 aria-expanded:opacity-100",
          viewed ? "bg-accent-soft" : "bg-hover",
        )}
        {...actions}
      />
    </div>
  );
}

function FolderRow({
  folder,
  depth,
  open,
  onToggle,
}: {
  folder: Folder;
  depth: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex h-6.5 items-center rounded-sm hover:bg-hover">
      <button
        type="button"
        title={folder.path}
        aria-expanded={open}
        onClick={onToggle}
        style={{ paddingLeft: 8 + depth * INDENT }}
        className={cn(ROW, "gap-1")}
      >
        <Icon
          name="chevron"
          className={cn(
            "text-ink-muted transition-transform",
            !open && "-rotate-90",
          )}
        />
        <Icon name="folder" className="text-ink-muted" />
        <span className="ml-0.5 min-w-10 flex-1 truncate">{folder.name}</span>
      </button>
    </div>
  );
}

/** A file tree in details view, like a file manager's: one line a file, folders first. */
function Details({
  root,
  searching,
  pending,
  ...picking
}: Picking & { root: Folder; searching: boolean; pending: ReactNode }) {
  const { state } = useAppState();
  const closed = new Set(state.closed_folders);
  const toggle = (path: string) =>
    updateAppState((current) => ({
      ...current,
      closed_folders: current.closed_folders.includes(path)
        ? current.closed_folders.filter((each) => each !== path)
        : [...current.closed_folders, path],
    }));
  const rows = (folder: Folder, depth: number): ReactNode[] => [
    ...folder.folders.flatMap((inside) => {
      // A search opens every folder, since what it found may be in a closed one.
      const open = searching || !closed.has(inside.path);
      return [
        <FolderRow
          key={`folder:${inside.path}`}
          folder={inside}
          depth={depth}
          open={open}
          onToggle={() => toggle(inside.path)}
        />,
        ...(open ? rows(inside, depth + 1) : []),
      ];
    }),
    ...folder.images.map((image) => (
      <FileRow key={image.name} image={image} depth={depth} {...picking} />
    )),
  ];
  return (
    <>
      <div className="sticky top-0 z-10 mb-0.5 flex h-6 items-center gap-2 border-b border-line bg-panel pr-2 pl-6.5 mono-annotation text-ink-muted">
        <span className="min-w-10 flex-1 truncate">Name</span>
        <span className={COLUMNS.size}>Size</span>
        <span className={COLUMNS.saved}>Saved</span>
        <span className={COLUMNS.changed}>Changed</span>
      </div>
      {pending}
      {rows(root, 0)}
    </>
  );
}

/** The images as a grid of previews, under the folder each is in. */
function Grid({
  root,
  pending,
  current,
  onSelect,
  ...actions
}: Picking & { root: Folder; pending: ReactNode }) {
  return (
    <>
      {pending}
      {foldersWithImages(root).map((folder) => (
        <section key={folder.path}>
          {folder.path && (
            <h3
              title={folder.path}
              className="mt-1 flex h-7 items-center gap-1.5 px-2 mono-annotation text-ink-muted"
            >
              <Icon name="folder" />
              <span className="truncate">{folder.path}</span>
            </h3>
          )}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-1.5 p-0.5">
            {folder.images.map((image) => {
              const viewed = current === image.name;
              return (
                <div
                  key={image.name}
                  className={cn(
                    "group relative min-w-0 rounded-md",
                    viewed ? "bg-accent-soft" : "hover:bg-hover",
                  )}
                >
                  <button
                    type="button"
                    title={image.name}
                    aria-current={viewed || undefined}
                    onClick={() => onSelect(image.name)}
                    className="flex w-full cursor-default flex-col gap-1 rounded-md p-1 text-left focus-visible:focus-ring focus-visible:outline-none"
                  >
                    <Thumb
                      picture={filePicture(image, true)}
                      shape={image}
                      animated={(image.frames ?? 1) > 1}
                      className="aspect-square w-full"
                    />
                    <span className="flex items-center gap-1 text-caption font-medium">
                      {image.status === "running" && <LoadingMark />}
                      {image.status !== null && failed(image.status) && (
                        <Icon
                          name="warning"
                          label="Failed"
                          className="text-danger"
                        />
                      )}
                      <span className="truncate">{baseName(image.name)}</span>
                    </span>
                  </button>
                  <ImageMenu
                    name={image.name}
                    className="absolute top-2 right-2 bg-panel opacity-0 group-hover:opacity-100 focus-visible:opacity-100 aria-expanded:opacity-100"
                    {...actions}
                  />
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </>
  );
}

/** The pane on the left: the images in the app's directory, over the directory they are kept in. */
export function ImagesPane({
  listing,
  creating,
  search,
  ...picking
}: Picking & {
  listing: ImageListing | null;
  /** Whether a new image is being described, which then has its own line at the top. */
  creating: boolean;
  /** The search field, so a key can put focus in it. */
  search: RefObject<HTMLInputElement | null>;
}) {
  const [query, setQuery] = useState("");
  const { settings } = useSettings();
  const grid = settings.images_view === "grid";
  const images = listing?.images ?? [];
  const found = matching(images, query);
  const root = folderTree(found);
  const pending = creating && (
    <div className="mb-px flex h-6.5 items-center gap-2 rounded-sm bg-accent-soft pr-2 pl-6.5 whitespace-nowrap">
      <span className="grid size-4.5 shrink-0 place-items-center rounded-[2px] border border-dashed border-line-control text-ink-muted">
        <Icon name="add" className="size-3" />
      </span>
      <span className="min-w-10 flex-1 truncate font-medium">New image</span>
    </div>
  );
  const toggle = grid ? "Show as details" : "Show as a grid";

  return (
    <nav
      aria-label="Your images"
      className="@container flex h-full min-w-0 flex-col bg-panel"
    >
      <header className="flex h-10 shrink-0 items-center gap-1.5 border-b border-line pr-2 pl-3">
        <h2 className="flex-1 truncate text-label">Your images</h2>
        <Tooltip content={toggle}>
          <Button
            size="sm"
            icon
            aria-label={toggle}
            onClick={() =>
              updateSettings((current) => ({
                ...current,
                images_view: grid ? "details" : "grid",
              }))
            }
          >
            <Icon name={grid ? "list" : "grid"} />
          </Button>
        </Tooltip>
      </header>
      <label className="m-2 flex h-7 shrink-0 items-center gap-2 rounded-sm border border-line-control bg-field pr-1.5 pl-2 transition-[background-color,border-color] focus-within:border-ink focus-within:bg-panel">
        <Icon name="search" className="text-ink-muted" />
        <input
          ref={search}
          value={query}
          placeholder="Search images"
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
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {grid ? (
          <Grid root={root} pending={pending} {...picking} />
        ) : (
          <Details
            root={root}
            searching={query.trim() !== ""}
            pending={pending}
            {...picking}
          />
        )}
        {found.length === 0 && query.trim() !== "" && (
          <p className="px-3 py-2 text-ink-muted">
            No images match {query.trim()}.
          </p>
        )}
      </div>
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
