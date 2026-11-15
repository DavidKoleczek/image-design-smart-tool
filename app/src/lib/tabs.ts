import { useSyncExternalStore } from "react";

import type { AppMethod, AppTab, ImageListing } from "@/lib/api";
import { clearGuides, type CanvasMode } from "@/lib/canvas";
import { dropDraft, newImageKey, updateDraft } from "@/lib/drafts";
import { dropDrawing } from "@/lib/drawing";
import { recordShown, type Brought } from "@/lib/images";
import { folderOf, movedPath } from "@/lib/paths";
import { clearReferences } from "@/lib/references";
import { onGone, onRenamed } from "@/lib/renames";
import { isDrawing } from "@/lib/request";
import { appStateNow, updateAppState } from "@/lib/state";

/**
 * An image open in the app, or a new image being described, with what was picked for it. Each tab keeps its own, so
 * going to another and back leaves it as it was.
 */
export type Tab = {
  id: string;
  /** The image's name in the directory; null for a new image. */
  image: string | null;
  /** Whether the next image opened takes its place, since nothing was done in it yet. */
  preview: boolean;
  method: AppMethod;
  /** What on the canvas guides its request, as picked; the image or the model may take only the other. */
  mode: CanvasMode;
  /** The version in view, by its id; null for what the image's file holds. */
  version: string | null;
};

type Tabs = { tabs: Tab[]; active: string | null };

/** Opened in the preview tab, which the next image opened takes, or in a tab of its own that stays. */
export type Opening = "preview" | "keep";

const listeners = new Set<() => void>();
let tabs: Tabs = { tabs: [], active: null };
// The data directory whose images the tabs are of, once they are opened for it.
let directory: string | null = null;
let made = 0;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function activeOf(state: Tabs): Tab | null {
  return state.tabs.find((tab) => tab.id === state.active) ?? null;
}

/** The images open in tabs as the app keeps them for the directory. */
function kept(state: Tabs): AppTab[] {
  return state.tabs.flatMap((tab) =>
    tab.image === null ? [] : [{ name: tab.image, preview: tab.preview }],
  );
}

function same(a: AppTab[], b: AppTab[]): boolean {
  return (
    a.length === b.length &&
    a.every(
      (tab, index) =>
        tab.name === b[index].name && tab.preview === b[index].preview,
    )
  );
}

/** Change the tabs. With `record`, an image that comes into view is recorded as the one the app shows. */
function set(next: Tabs, record = true) {
  const before = activeOf(tabs)?.image ?? null;
  tabs = next;
  const after = activeOf(next)?.image ?? null;
  if (record && after !== null && after !== before) {
    recordShown(after);
  }
  const open = kept(next);
  if (directory !== null && !same(open, appStateNow().tabs)) {
    updateAppState((current) => ({ ...current, tabs: open }));
  }
  for (const listener of listeners) {
    listener();
  }
}

function newId(): string {
  made += 1;
  return `${made}`;
}

function imageTab(name: string, preview: boolean): Tab {
  return {
    id: newId(),
    image: name,
    preview,
    method: isDrawing(name) ? "svg" : "model",
    mode: "markup",
    version: null,
  };
}

/** A tab for a new image that goes in `folder`, "" for the top, made the way a new image was made last. */
function newTab(folder: string): Tab {
  const tab: Tab = {
    id: newId(),
    image: null,
    preview: false,
    method: appStateNow().method,
    mode: "markup",
    version: null,
  };
  updateDraft(newImageKey(tab.id), { folder });
  return tab;
}

/** The tabs with `tab` after the one in view, which it becomes. */
function added(tab: Tab): Tabs {
  const at = tabs.tabs.findIndex((each) => each.id === tabs.active);
  const list = tabs.tabs.slice();
  list.splice(at + 1, 0, tab);
  return { tabs: list, active: tab.id };
}

/** What a tab's request, its marks, and its references are kept under: its image's name, or its new image's key. */
export function keyOf(tab: Tab): string {
  return tab.image ?? newImageKey(tab.id);
}

/** The id of what a tab shows, which the tab names. */
export function tabPanelId(tab: Tab): string {
  return `tab-panel-${tab.id}`;
}

/**
 * Open the tabs the app kept for the directory listed, once it is listed and what was picked there is read. The tab
 * in view is the image the app showed last, else the first tab, else the first image; a directory with none starts
 * on a new image.
 */
export function openTabs(listing: ImageListing) {
  if (listing.data_directory === directory) {
    return;
  }
  directory = listing.data_directory;
  const names = new Set(listing.images.map((image) => image.name));
  const seen = new Set<string>();
  let preview = false;
  const open: Tab[] = [];
  for (const { name, preview: previewed } of appStateNow().tabs) {
    if (names.has(name) && !seen.has(name)) {
      seen.add(name);
      // There is one preview tab at most, whatever was saved.
      open.push(imageTab(name, previewed && !preview));
      preview ||= previewed;
    }
  }
  const shown = listing.shown;
  if (shown !== null && names.has(shown) && !seen.has(shown)) {
    open.push(imageTab(shown, !preview));
  }
  const first = listing.images.at(0);
  if (open.length === 0) {
    open.push(first ? imageTab(first.name, true) : newTab(""));
  }
  const active = open.find((tab) => tab.image === shown) ?? open[0];
  // What shows is what the app showed, or what it opens on when it showed none, so there is nothing to record.
  set({ tabs: open, active: active.id }, false);
}

/**
 * Bring an image into view in its tab. One not open yet takes the preview tab, or a tab of its own after the one in
 * view when `how` is `keep` or there is no preview tab. Opening one already open with `keep` keeps its tab.
 */
export function openImage(name: string, how: Opening = "preview") {
  const open = tabs.tabs.find((tab) => tab.image === name);
  if (open) {
    set({
      tabs:
        how === "keep" && open.preview
          ? tabs.tabs.map((tab) =>
              tab === open ? { ...tab, preview: false } : tab,
            )
          : tabs.tabs,
      active: open.id,
    });
    return;
  }
  const tab = imageTab(name, how === "preview");
  const preview =
    how === "preview" ? tabs.tabs.find((each) => each.preview) : undefined;
  set(
    preview
      ? {
          tabs: tabs.tabs.map((each) => (each === preview ? tab : each)),
          active: tab.id,
        }
      : added(tab),
  );
}

/** Bring up an image the server was asked to, once the tabs are of its directory. */
export function bringUp(brought: Brought) {
  if (brought.dataDirectory === directory) {
    openImage(brought.name);
  }
}

/** Open a tab for a new image that goes in `folder`, "" for the top, and return it. */
export function openNew(folder: string): Tab {
  const tab = newTab(folder);
  set(added(tab));
  return tab;
}

export function activateTab(id: string) {
  if (id !== tabs.active && tabs.tabs.some((tab) => tab.id === id)) {
    set({ ...tabs, active: id });
  }
}

/** Keep a tab from being taken by the next image opened, as once something is done in it. */
export function keepTab(id: string) {
  if (tabs.tabs.some((tab) => tab.id === id && tab.preview)) {
    set({
      ...tabs,
      tabs: tabs.tabs.map((tab) =>
        tab.id === id ? { ...tab, preview: false } : tab,
      ),
    });
  }
}

/** Change what was picked in a tab. */
export function updateTab(
  id: string,
  change: Partial<Pick<Tab, "method" | "mode" | "version">>,
) {
  const tab = tabs.tabs.find((each) => each.id === id);
  if (
    tab &&
    (Object.keys(change) as (keyof typeof change)[]).some(
      (key) => change[key] !== tab[key],
    )
  ) {
    set({
      ...tabs,
      tabs: tabs.tabs.map((each) =>
        each.id === id ? { ...each, ...change } : each,
      ),
    });
  }
}

/** A tab's new image was created as the image named `name`, which it shows from now on. */
export function createdIn(id: string, name: string) {
  set({
    ...tabs,
    tabs: tabs.tabs.map((tab) =>
      tab.id === id
        ? { ...tab, image: name, preview: false, version: null }
        : tab,
    ),
  });
}

/** Forget what was in progress in a tab that closes, so its image opens again as it is. */
function forget(tab: Tab) {
  const key = keyOf(tab);
  dropDraft(key);
  clearReferences(key);
  clearGuides(key);
  dropDrawing(key);
}

/**
 * Close a tab. The one after it comes into view, or the one before when it was the last. Closing the only tab leaves a
 * new image in the folder it showed.
 */
export function closeTab(id: string) {
  const at = tabs.tabs.findIndex((tab) => tab.id === id);
  if (at < 0) {
    return;
  }
  const closing = tabs.tabs[at];
  forget(closing);
  const left = tabs.tabs.filter((tab) => tab.id !== id);
  if (left.length === 0) {
    left.push(newTab(folderOf(closing.image ?? "")));
  }
  const active =
    tabs.active === id
      ? (left[Math.min(at, left.length - 1)]?.id ?? null)
      : tabs.active;
  set({ tabs: left, active });
}

/**
 * Close the tabs `closing` says to, keeping the tab `id`, which comes into view when the one in view was closed.
 */
function closeAround(
  id: string,
  closing: (tab: Tab, index: number) => boolean,
) {
  const at = tabs.tabs.findIndex((tab) => tab.id === id);
  if (at < 0) {
    return;
  }
  const closed = tabs.tabs.filter(
    (tab, index) => tab.id !== id && closing(tab, index),
  );
  if (closed.length === 0) {
    return;
  }
  closed.forEach(forget);
  const left = tabs.tabs.filter((tab) => !closed.includes(tab));
  set({
    tabs: left,
    active: left.some((tab) => tab.id === tabs.active) ? tabs.active : id,
  });
}

/** Close every tab but `id`. */
export function closeOtherTabs(id: string) {
  closeAround(id, () => true);
}

/** Close the tabs after `id`. */
export function closeTabsAfter(id: string) {
  const at = tabs.tabs.findIndex((tab) => tab.id === id);
  closeAround(id, (_, index) => index > at);
}

// A tab stays on its image under the name it has now.
onRenamed((from, to) => {
  if (
    tabs.tabs.some(
      (tab) =>
        tab.image !== null && movedPath(tab.image, from, to) !== tab.image,
    )
  ) {
    set({
      ...tabs,
      tabs: tabs.tabs.map((tab) =>
        tab.image === null
          ? tab
          : { ...tab, image: movedPath(tab.image, from, to) },
      ),
    });
  }
});

// A tab on an image that was deleted has nothing to show, and an image made later under its name starts with nothing
// of what was in progress there.
onGone((name) => {
  for (const tab of tabs.tabs.filter((each) => each.image === name)) {
    closeTab(tab.id);
  }
});

/** The tabs open, in the order they show, and the one in view. */
export function useTabs(): Tabs & { current: Tab | null } {
  const state = useSyncExternalStore(subscribe, () => tabs);
  return { ...state, current: activeOf(state) };
}
