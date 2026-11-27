import { Activity, useEffect, useRef, useState } from "react";
import { usePanelRef } from "react-resizable-panels";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { DeleteDialog, RenameDialog } from "@/components/ImageMenu";
import { ImagesPane } from "@/components/ImagesPane";
import { ImageSwitcher } from "@/components/ImageSwitcher";
import { KeyDialog } from "@/components/KeyDialog";
import { Panes } from "@/components/Panes";
import { SettingsMenu } from "@/components/SettingsMenu";
import { ShortcutsDialog } from "@/components/ShortcutsDialog";
import { StatusBar } from "@/components/StatusBar";
import { TabStrip } from "@/components/TabStrip";
import { TabView } from "@/components/TabView";
import { TopBar, type NarrowPane, type Pane } from "@/components/TopBar";
import { Segmented } from "@/components/ui/segmented";
import { AppMark, Wordmark } from "@/components/Wordmark";
import { WorkspacePicker } from "@/components/WorkspacePicker";
import { fitTool, type CanvasMode } from "@/lib/canvas";
import { draftOf, updateDraft, useDraft } from "@/lib/drafts";
import { useGuidance } from "@/lib/guidance";
import { onDisplay, requestDisplayMode } from "@/lib/host";
import { useImages } from "@/lib/images";
import { paneLayout, useBreakpoint } from "@/lib/layout";
import { folderOf } from "@/lib/paths";
import { addEntries, referencesOf } from "@/lib/references";
import { renamed } from "@/lib/renames";
import { folderIn } from "@/lib/request";
import { updateSettings, useSettings } from "@/lib/settings";
import { useShortcuts } from "@/lib/shortcuts";
import { loadAppState } from "@/lib/state";
import {
  activateTab,
  bringUp,
  closeOtherTabs,
  closeTab,
  closeTabsAfter,
  keepTab,
  keyOf,
  moveTab,
  openImage,
  openNew,
  openTabs,
  updateTab,
  useTabs,
} from "@/lib/tabs";
import type { Entry } from "@/lib/tree";
import { cn } from "@/lib/utils";
import { viewed } from "@/lib/viewed";
import { useWorkspaces, useWorkspaceWait } from "@/lib/workspaces";

type Display = { fullscreen: boolean; expandable: boolean };

/**
 * The workspace the app shows, or picking one first when it shows none. Everything of a workspace mounts afresh for
 * each, so nothing of the last one shows in the next.
 */
function App() {
  const [display, setDisplay] = useState<Display>({
    fullscreen: false,
    expandable: false,
  });
  const { shown } = useWorkspaces();
  useWorkspaceWait(shown === null);

  useEffect(
    () =>
      onDisplay(({ mode, available }) =>
        setDisplay({
          fullscreen: mode === "fullscreen",
          expandable: mode !== "fullscreen" && available.includes("fullscreen"),
        }),
      ),
    [],
  );

  return shown === null ? (
    <FirstStep fullscreen={display.fullscreen} />
  ) : (
    <InWorkspace key={shown} display={display} />
  );
}

/** Picking a workspace, in place of everything else, until the app shows one. */
function FirstStep({ fullscreen }: { fullscreen: boolean }) {
  const [root, breakpoint] = useBreakpoint();
  return (
    <div
      ref={root}
      className={cn(
        "flex flex-col overflow-hidden bg-canvas text-ink",
        fullscreen ? "h-dvh" : "h-140",
      )}
    >
      <header className="flex h-11 shrink-0 items-center gap-2 border-b border-line bg-panel pr-2 pl-3">
        {breakpoint === "narrow" ? (
          <AppMark />
        ) : (
          <h1 className="flex shrink-0 items-center">
            <Wordmark />
          </h1>
        )}
        <span className="flex-1" />
        <SettingsMenu />
      </header>
      <main className="flex min-h-0 flex-1 justify-center overflow-y-auto px-4 py-8">
        <section
          aria-labelledby="choose-workspace"
          className="w-full max-w-110"
        >
          <h2 id="choose-workspace" className="text-title">
            Choose a workspace
          </h2>
          <p className="mt-1 mb-4 text-ink-muted">
            Your project's top-level folder. The app keeps its images in the
            folder's .image-design.
          </p>
          <WorkspacePicker />
        </section>
      </main>
      <KeyDialog />
    </div>
  );
}

/** The images of the workspace the app shows, the tabs open on them, and their requests. */
function InWorkspace({ display }: { display: Display }) {
  const [root, breakpoint, width] = useBreakpoint();
  const [narrowPane, setNarrowPane] = useState<NarrowPane>("image");
  const [shortcuts, setShortcuts] = useState(false);
  const { listing, error, brought, refresh } = useImages();
  const { tabs, active, current: tab } = useTabs();
  const images = new Map(
    (listing?.images ?? []).map((each) => [each.name, each]),
  );
  // The tab in view, whose image and mode the bars around the tabs show.
  const image = tab?.image ? (images.get(tab.image) ?? null) : null;
  const { shown } = viewed(image, tab?.version ?? null);
  const { blocks, mode } = useGuidance(tab, image, shown);
  const draft = useDraft(tab ? keyOf(tab) : "");
  // The folder the new image in view goes in, which Your images shows it in.
  const creating =
    listing !== null && tab?.image === null && listing.images.length > 0
      ? folderIn(listing, draft.folder)
      : null;
  // The image a dialog is asking to rename, by its name, and the images and folders one is asking to delete.
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Entry[] | null>(null);
  const search = useRef<HTMLInputElement>(null);
  // The folder a new image goes in by default: the one selected in Your images, or the one its selection is in.
  const here = useRef<string | null>(null);
  // Whether the workspace's picks are read, so its tabs can open as they were left.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let current = true;
    void loadAppState().then(() => {
      if (current) {
        setReady(true);
      }
    });
    return () => {
      current = false;
    };
  }, []);
  useEffect(() => {
    if (listing !== null && ready) {
      openTabs(listing);
    }
  }, [listing, ready]);
  useEffect(() => {
    if (brought !== null) {
      bringUp(brought);
    }
  }, [brought]);
  // The tool picked fits what the canvas of the tab in view is for.
  useEffect(() => {
    if (mode !== null) {
      fitTool(mode);
    }
  }, [mode, active]);
  const { settings } = useSettings();
  const panes = { images: usePanelRef(), request: usePanelRef() };
  // A pane opened or closed from the top bar, which the next layout change saves like a drag.
  const toggled = useRef(false);

  const layoutKey = breakpoint === "wide" ? "wide" : "medium";
  const layout = settings[layoutKey];

  const saveLayout = (pane: Pane, size: number, user: boolean) => {
    if (!user && !toggled.current) {
      return;
    }
    toggled.current = false;
    updateSettings((current) => ({
      ...current,
      [layoutKey]: {
        ...current[layoutKey],
        [pane]: paneLayout(size, current[layoutKey][pane]),
      },
    }));
  };

  const togglePane = (pane: Pane) => {
    const panel = panes[pane].current;
    if (!panel) {
      return;
    }
    toggled.current = true;
    if (panel.isCollapsed()) {
      panel.expand();
    } else {
      panel.collapse();
    }
  };

  const pickMode = (picked: CanvasMode) => {
    if (tab && blocks[picked] === null) {
      updateTab(tab.id, { mode: picked });
      keepTab(tab.id);
    }
  };

  /** The folder a new image goes in by default: the one selected in Your images, or the one the tab in view is in. */
  const newFolder = (): string =>
    here.current ??
    (tab?.image ? folderOf(tab.image) : folderIn(listing, draft.folder));

  /**
   * Start a new image in `folder`, by default the folder selected in Your images, or the one the image in view, or the
   * new image in view, is in. A new image in view with nothing written for it yet is the one started. Returns what its
   * request is kept under.
   */
  const startNew = (folder?: string): string => {
    const where = folder ?? newFolder();
    if (tab && tab.image === null) {
      const key = keyOf(tab);
      const draft = draftOf(key);
      if (
        draft.prompt.trim() === "" &&
        draft.name === null &&
        referencesOf(key).length === 0
      ) {
        updateDraft(key, { folder: where });
        return key;
      }
    }
    return keyOf(openNew(where));
  };

  /** Add an image of the directory to the references of a request, which `key` names. */
  const refer = (name: string, key: string) => {
    const added = images.get(name);
    if (added) {
      addEntries(key, [{ name: added.name, path: added.path }], Infinity);
    }
  };

  useShortcuts({
    "1": () => pickMode("markup"),
    "2": () => pickMode("mask"),
    "[": () => breakpoint === "wide" && togglePane("images"),
    "]": () => breakpoint !== "narrow" && togglePane("request"),
    n: () => startNew(),
    "/": () => {
      if (breakpoint !== "wide") {
        return;
      }
      const pane = panes.images.current;
      if (pane?.isCollapsed()) {
        toggled.current = true;
        pane.expand();
      }
      // Once the pane is open again, when it was closed.
      requestAnimationFrame(() => search.current?.focus());
    },
    "?": () => setShortcuts(true),
  });

  const picking = {
    onSelect: (name: string) => openImage(name),
    onOpenTab: (name: string) => openImage(name, "keep"),
    onUseInNew: (name: string) => refer(name, startNew()),
    onAddReference: (name: string) => tab && refer(name, keyOf(tab)),
    source: image?.name ?? null,
  };
  const narrow = breakpoint === "narrow" ? narrowPane : null;
  const work = (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <TabStrip
        tabs={tabs}
        active={active}
        images={images}
        onActivate={activateTab}
        onKeep={keepTab}
        onClose={closeTab}
        onCloseOthers={closeOtherTabs}
        onCloseAfter={closeTabsAfter}
        onMove={moveTab}
        onNew={() => startNew()}
      />
      {tabs.map((each) => (
        <Activity
          key={each.id}
          mode={each.id === active ? "visible" : "hidden"}
        >
          <TabView
            tab={each}
            active={each.id === active}
            listing={listing}
            error={error}
            wide={breakpoint === "wide"}
            narrow={narrow}
            layout={layout}
            width={width}
            requestPanel={panes.request}
            onLayout={(size, user) => saveLayout("request", size, user)}
            onUseInNew={picking.onUseInNew}
            onRefresh={refresh}
          />
        </Activity>
      ))}
    </div>
  );

  return (
    <div
      ref={root}
      className={cn(
        "flex flex-col overflow-hidden bg-canvas text-ink",
        display.fullscreen ? "h-dvh" : "h-140",
      )}
    >
      <TopBar
        breakpoint={breakpoint}
        image={image}
        switcher={
          <ImageSwitcher
            listing={listing}
            image={image}
            onNew={() => startNew()}
            onRename={setRenaming}
            onDelete={(name) => setDeleting([{ path: name, folder: false }])}
            {...picking}
          />
        }
        panes={{ images: layout.images.open, request: layout.request.open }}
        onTogglePane={togglePane}
        narrowPane={narrowPane}
        onNarrowPane={setNarrowPane}
        onNew={() => startNew()}
        onExpand={
          display.expandable
            ? () => void requestDisplayMode("fullscreen")
            : undefined
        }
        onShortcuts={() => setShortcuts(true)}
        center={
          <Segmented<CanvasMode>
            label="Canvas mode"
            value={mode}
            onChange={pickMode}
            options={[
              {
                value: "markup",
                label: "Markup",
                icon: "mark",
                disabled: blocks.markup ?? undefined,
              },
              {
                value: "mask",
                label: "Mask",
                icon: "area",
                disabled: blocks.mask ?? undefined,
              },
            ]}
          />
        }
      />
      <main className="flex min-h-0 flex-1">
        <ErrorBoundary what="This view" className="m-4 flex-1">
          {breakpoint === "wide" ? (
            <Panes
              layout={layout}
              width={width}
              imagesPanel={panes.images}
              images={
                <ImagesPane
                  listing={listing}
                  current={image?.name ?? null}
                  creating={creating}
                  search={search}
                  hereRef={here}
                  onNew={startNew}
                  newFolder={newFolder}
                  onRemove={setDeleting}
                  onChanged={refresh}
                  {...picking}
                />
              }
              tabs={work}
              onChanged={(size, user) => saveLayout("images", size, user)}
            />
          ) : (
            work
          )}
        </ErrorBoundary>
      </main>
      {breakpoint === "wide" && display.fullscreen && (
        <StatusBar listing={listing} image={image} shown={shown} />
      )}
      <ShortcutsDialog open={shortcuts} onOpenChange={setShortcuts} />
      <KeyDialog />
      <RenameDialog
        name={renaming}
        onClose={() => setRenaming(null)}
        onRenamed={(name) => {
          if (renaming !== null) {
            renamed(renaming, name);
          }
          void refresh();
        }}
      />
      <DeleteDialog entries={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}

export default App;
