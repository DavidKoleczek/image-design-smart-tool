import { useEffect, useRef, useState } from "react";
import { usePanelRef } from "react-resizable-panels";

import { Canvas } from "@/components/Canvas";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { DeleteDialog, RenameDialog } from "@/components/ImageMenu";
import { ImagesPane } from "@/components/ImagesPane";
import { ImageSwitcher } from "@/components/ImageSwitcher";
import { KeyDialog } from "@/components/KeyDialog";
import { RequestPane } from "@/components/RequestPane";
import { ShortcutsDialog } from "@/components/ShortcutsDialog";
import { StatusBar } from "@/components/StatusBar";
import { TopBar, type NarrowPane, type Pane } from "@/components/TopBar";
import { Segmented } from "@/components/ui/segmented";
import { Workspace } from "@/components/Workspace";
import { clearGuides, setMode, useCanvas, type CanvasMode } from "@/lib/canvas";
import { onDisplay, requestDisplayMode } from "@/lib/host";
import { NEW_IMAGE, updateDraft, useDraft } from "@/lib/drafts";
import { sentDrawing } from "@/lib/drawing";
import { useImages } from "@/lib/images";
import { paneLayout, useBreakpoint } from "@/lib/layout";
import { useMethods } from "@/lib/methods";
import { addEntries, clearReferences } from "@/lib/references";
import { onGone, renamed } from "@/lib/renames";
import {
  guideBlock,
  isDrawing,
  kindOf,
  makesNew,
  pickedModel,
} from "@/lib/request";
import { useRuns } from "@/lib/runs";
import { updateSettings, useLayoutResets, useSettings } from "@/lib/settings";
import { useShortcuts } from "@/lib/shortcuts";
import {
  appStateNow,
  followDirectory,
  updateAppState,
  useAppState,
} from "@/lib/state";
import type { Entry } from "@/lib/tree";
import { cn } from "@/lib/utils";
import { useViewed } from "@/lib/viewed";

function App() {
  const [root, breakpoint, width] = useBreakpoint();
  const [display, setDisplay] = useState({
    fullscreen: false,
    expandable: false,
  });
  const [narrowPane, setNarrowPane] = useState<NarrowPane>("image");
  const [shortcuts, setShortcuts] = useState(false);
  const { mode: pickedMode } = useCanvas();
  const { listing, image, error, startNew, select, refresh } = useImages();
  const { shown, before, view } = useViewed(image);
  const runs = useRuns(image);
  const { state } = useAppState();
  const { methods } = useMethods();
  const method = state.method;
  const model =
    methods && method === "model" ? pickedModel(state.request, methods) : null;
  const draft = useDraft(image?.name ?? NEW_IMAGE);
  // A request that makes a new image from the one in view takes neither marks nor a mask.
  const fresh =
    image !== null &&
    methods !== null &&
    makesNew(
      image,
      method,
      model,
      methods,
      kindOf(image, draft.kind, state.request, model),
    );
  const blocks: Record<CanvasMode, string | null> = {
    markup: guideBlock("markup", image, shown, model, fresh),
    mask: guideBlock("mask", image, shown, model, fresh),
  };
  // Marks drawn while an agent draws the image go to it with the next message.
  const steering = method === "svg" && image !== null && isDrawing(image.name);
  // A mode the image or the model does not take gives way to marks, which every model takes.
  const mode: CanvasMode | null =
    blocks[pickedMode] === null
      ? pickedMode
      : blocks.markup === null
        ? "markup"
        : null;
  // The image a dialog is asking to rename, by its name, and the images and folders one is asking to delete.
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Entry[] | null>(null);
  // So an image made later under the name of one that was deleted starts with nothing of that one.
  useEffect(
    () =>
      onGone((name) => {
        updateDraft(name, { prompt: "", size: null });
        clearReferences(name);
        clearGuides(name);
        sentDrawing(name);
      }),
    [],
  );
  const search = useRef<HTMLInputElement>(null);
  const dataDirectory = listing?.data_directory ?? null;
  useEffect(() => followDirectory(dataDirectory), [dataDirectory]);
  const viewing = image?.name ?? null;
  // An image opens on the method that made it: a drawing on SVG, anything else on an image model.
  useEffect(() => {
    if (viewing === null) {
      return;
    }
    const made = isDrawing(viewing) ? "svg" : "model";
    if (appStateNow().method !== made) {
      updateAppState((current) => ({ ...current, method: made }));
    }
  }, [viewing]);
  const { settings } = useSettings();
  const resets = useLayoutResets();
  const panes = { images: usePanelRef(), request: usePanelRef() };
  // A pane opened or closed from the top bar, which the next layout change saves like a drag.
  const toggled = useRef(false);

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

  const layoutKey = breakpoint === "wide" ? "wide" : "medium";
  const layout = settings[layoutKey];

  const saveLayout = (
    widths: Record<"images" | "request", number>,
    user: boolean,
  ) => {
    if (!user && !toggled.current) {
      return;
    }
    toggled.current = false;
    updateSettings((current) => ({
      ...current,
      [layoutKey]: {
        images:
          breakpoint === "wide"
            ? paneLayout(widths.images, current[layoutKey].images)
            : current[layoutKey].images,
        request: paneLayout(widths.request, current[layoutKey].request),
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
    if (blocks[picked] === null) {
      setMode(picked);
    }
  };

  /** Add an image of the directory to the references of a request, which `key` names. */
  const refer = (name: string, key: string) => {
    const added = listing?.images.find((each) => each.name === name);
    if (added) {
      addEntries(key, [{ name: added.name, path: added.path }], Infinity);
    }
  };

  useShortcuts({
    "1": () => pickMode("markup"),
    "2": () => pickMode("mask"),
    "[": () => breakpoint === "wide" && togglePane("images"),
    "]": () => breakpoint !== "narrow" && togglePane("request"),
    n: startNew,
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
    onSelect: select,
    onUseInNew: (name: string) => {
      refer(name, NEW_IMAGE);
      startNew();
    },
    onAddReference: (name: string) =>
      refer(name, image ? image.name : NEW_IMAGE),
    source: image?.name ?? null,
  };
  const canvas = (
    <Canvas
      listing={listing}
      image={image}
      shown={shown}
      before={before}
      runs={runs}
      mode={mode}
      tools={mode ?? "markup"}
      blocked={mode === null ? blocks.markup : null}
      steering={steering}
      error={error}
      onView={view}
      onChanged={refresh}
    />
  );
  const request = (
    <RequestPane
      listing={listing}
      image={image}
      shown={shown}
      runs={runs}
      mode={mode}
      onUseInNew={picking.onUseInNew}
      onCreated={async (name) => {
        // Listed first, so the image is there to come into view.
        await refresh();
        select(name);
      }}
      onChanged={refresh}
      onView={view}
    />
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
            onNew={startNew}
            onRename={setRenaming}
            onDelete={(name) => setDeleting([{ path: name, folder: false }])}
            {...picking}
          />
        }
        panes={{ images: layout.images.open, request: layout.request.open }}
        onTogglePane={togglePane}
        narrowPane={narrowPane}
        onNarrowPane={setNarrowPane}
        onNew={startNew}
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
        <ErrorBoundary what="The workspace" className="m-4 flex-1">
          {breakpoint === "narrow" ? (
            <div className="flex min-w-0 flex-1 flex-col">
              {narrowPane === "image" ? canvas : request}
            </div>
          ) : (
            <Workspace
              key={`${layoutKey}-${resets}`}
              wide={breakpoint === "wide"}
              layout={layout}
              width={width}
              panes={panes}
              images={
                <ImagesPane
                  listing={listing}
                  current={image?.name ?? null}
                  creating={
                    listing !== null &&
                    image === null &&
                    listing.images.length > 0
                  }
                  search={search}
                  onNew={startNew}
                  onRemove={setDeleting}
                  onChanged={refresh}
                  {...picking}
                />
              }
              canvas={canvas}
              request={request}
              onChanged={saveLayout}
            />
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
