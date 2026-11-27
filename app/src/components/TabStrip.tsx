import {
  useEffect,
  useRef,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
  MenuItem,
} from "@/components/ui/menu";
import { Thumb } from "@/components/ui/thumb";
import { Tooltip } from "@/components/ui/tooltip";
import type { ImageSummary } from "@/lib/api";
import { useDraft } from "@/lib/drafts";
import { baseName } from "@/lib/paths";
import { filePicture } from "@/lib/pictures";
import { useReorder } from "@/lib/reorder";
import { keyOf, tabPanelId, type Tab } from "@/lib/tabs";
import { cn } from "@/lib/utils";

function TabItem({
  tab,
  image,
  current,
  others,
  after,
  dragging,
  onDragStart,
  onActivate,
  onKeep,
  onClose,
  onCloseOthers,
  onCloseAfter,
}: {
  tab: Tab;
  /** The image the tab shows; none for a new image, or one not listed yet. */
  image: ImageSummary | null;
  current: boolean;
  /** Whether there are other tabs, and whether any of them are after this one. */
  others: boolean;
  after: boolean;
  /** Whether it is being dragged along the strip. */
  dragging: boolean;
  onDragStart: (event: PointerEvent) => void;
  onActivate: () => void;
  onKeep: () => void;
  onClose: () => void;
  onCloseOthers: () => void;
  onCloseAfter: () => void;
}) {
  const draft = useDraft(keyOf(tab));
  const item = useRef<HTMLDivElement>(null);
  // The tab in view is brought into the strip, as when it opens past its end.
  useEffect(() => {
    if (current) {
      item.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [current]);
  const label = tab.image ? baseName(tab.image) : "New image";
  const where = tab.image ?? `New image in ${draft.folder || "/"}`;
  return (
    <ContextMenu>
      <ContextMenuTrigger
        ref={item}
        role="presentation"
        onPointerDown={onDragStart}
        className={cn(
          "group relative flex h-full max-w-56 min-w-24 shrink-0 items-center border-r border-line select-none",
          current
            ? "-mb-px bg-canvas text-ink"
            : "text-ink-muted hover:bg-hover",
          dragging && "z-10 shadow-popover",
        )}
      >
        {current && (
          <span
            aria-hidden
            className="absolute inset-x-0 top-0 h-0.5 bg-accent"
          />
        )}
        <button
          type="button"
          role="tab"
          id={`tab-${tab.id}`}
          aria-selected={current}
          aria-controls={tabPanelId(tab)}
          tabIndex={current ? 0 : -1}
          title={where}
          // A press brings the tab into view, as in a browser, so one dragged is the one that shows.
          onPointerDown={(event) => event.button === 0 && onActivate()}
          onClick={onActivate}
          onDoubleClick={onKeep}
          // The middle button closes a tab, as in a browser, rather than starting to scroll.
          onMouseDown={(event) => event.button === 1 && event.preventDefault()}
          onAuxClick={(event) => event.button === 1 && onClose()}
          className="flex h-full min-w-0 flex-1 cursor-default items-center gap-2 pr-1 pl-3 outline-none focus-visible:focus-ring"
        >
          {image?.status === "running" ? (
            <LoadingMark />
          ) : image ? (
            <Thumb
              picture={filePicture(image, true)}
              className="size-4 rounded-[2px]"
            />
          ) : (
            <span className="grid size-4 shrink-0 place-items-center rounded-[2px] border border-dashed border-line-control">
              <Icon name="add" className="size-3" />
            </span>
          )}
          <span className={cn("min-w-0 truncate", tab.preview && "italic")}>
            {label}
          </span>
        </button>
        <button
          type="button"
          aria-label={`Close ${label}`}
          title="Close"
          onClick={onClose}
          className={cn(
            "mr-1.5 grid size-5 shrink-0 place-items-center rounded-sm text-ink-muted hover:bg-hover hover:text-ink focus-visible:focus-ring focus-visible:outline-none",
            !current &&
              "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
          )}
        >
          <Icon name="close" />
        </button>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <MenuItem onClick={onClose}>Close</MenuItem>
        <MenuItem disabled={!others} onClick={onCloseOthers}>
          Close other tabs
        </MenuItem>
        <MenuItem disabled={!after} onClick={onCloseAfter}>
          Close all to the right
        </MenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

/**
 * The tabs open over the canvas and the request, one for each image being worked on, in the order they opened or were
 * dragged into. A tab opened by a click in Your images is a preview, in italics, which the next image opened takes
 * until something is done in it or it is double-clicked. A right click on a tab closes it, the others, or those after
 * it.
 */
export function TabStrip({
  tabs,
  active,
  images,
  onActivate,
  onKeep,
  onClose,
  onCloseOthers,
  onCloseAfter,
  onMove,
  onNew,
}: {
  tabs: Tab[];
  active: string | null;
  /** The images listed, by their names. */
  images: ReadonlyMap<string, ImageSummary>;
  onActivate: (id: string) => void;
  onKeep: (id: string) => void;
  onClose: (id: string) => void;
  onCloseOthers: (id: string) => void;
  onCloseAfter: (id: string) => void;
  /** Put a tab at an index among the tabs. */
  onMove: (id: string, index: number) => void;
  onNew: () => void;
}) {
  const list = useRef<HTMLDivElement>(null);
  const reorder = useReorder(list, true, onMove);

  // The arrows go to the tab beside, which comes into view, as in any list of tabs.
  const keys = (event: KeyboardEvent) => {
    const at = tabs.findIndex((tab) => tab.id === active);
    const by =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    const next =
      event.key === "Home"
        ? tabs[0]
        : event.key === "End"
          ? tabs.at(-1)
          : by !== 0
            ? tabs[(at + by + tabs.length) % tabs.length]
            : undefined;
    if (!next) {
      return;
    }
    event.preventDefault();
    onActivate(next.id);
    requestAnimationFrame(() =>
      list.current
        ?.querySelector<HTMLElement>(`#tab-${CSS.escape(next.id)}`)
        ?.focus(),
    );
  };

  return (
    <div className="flex h-9 shrink-0 border-b border-line bg-panel">
      <div
        ref={list}
        role="tablist"
        aria-label="Open images"
        onKeyDown={keys}
        className="flex min-w-0 scrollbar-none overflow-x-auto"
      >
        {tabs.map((tab, index) => (
          <TabItem
            key={tab.id}
            tab={tab}
            image={tab.image === null ? null : (images.get(tab.image) ?? null)}
            current={tab.id === active}
            others={tabs.length > 1}
            after={index < tabs.length - 1}
            dragging={reorder.dragging === tab.id}
            onDragStart={(event) => reorder.start(tab.id, event)}
            onActivate={() => onActivate(tab.id)}
            onKeep={() => onKeep(tab.id)}
            onClose={() => !reorder.dragged() && onClose(tab.id)}
            onCloseOthers={() => onCloseOthers(tab.id)}
            onCloseAfter={() => onCloseAfter(tab.id)}
          />
        ))}
      </div>
      <Tooltip content="New image" keys="N">
        <Button
          size="sm"
          icon
          aria-label="New image"
          onClick={onNew}
          className="mx-1.5 my-auto shrink-0"
        >
          <Icon name="add" />
        </Button>
      </Tooltip>
    </div>
  );
}
