import { useEffect, useRef, useState } from "react";
import { usePanelRef } from "react-resizable-panels";

import { Canvas } from "@/components/Canvas";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { DeleteDialog, RenameDialog } from "@/components/ImageMenu";
import { ImagesPane } from "@/components/ImagesPane";
import { ImageSwitcher } from "@/components/ImageSwitcher";
import { RequestPane } from "@/components/RequestPane";
import { ShortcutsDialog } from "@/components/ShortcutsDialog";
import { StatusBar } from "@/components/StatusBar";
import { TopBar, type NarrowPane, type Pane } from "@/components/TopBar";
import { Segmented } from "@/components/ui/segmented";
import { Workspace } from "@/components/Workspace";
import { onDisplay, requestDisplayMode } from "@/lib/host";
import { moveDraft } from "@/lib/drafts";
import { useImages } from "@/lib/images";
import { paneLayout, useBreakpoint } from "@/lib/layout";
import { useRuns } from "@/lib/runs";
import { updateSettings, useLayoutResets, useSettings } from "@/lib/settings";
import { useShortcuts } from "@/lib/shortcuts";
import { followDirectory } from "@/lib/state";
import { cn } from "@/lib/utils";
import { useViewed } from "@/lib/viewed";

/** What the canvas is for: marks and the mask are two ways to guide a request, and one shows at a time. */
type CanvasMode = "markup" | "mask";

const NEEDS_SOURCE = "Needs a source image";

function App() {
  const [root, breakpoint, width] = useBreakpoint();
  const [display, setDisplay] = useState({
    fullscreen: false,
    expandable: false,
  });
  const [narrowPane, setNarrowPane] = useState<NarrowPane>("image");
  const [shortcuts, setShortcuts] = useState(false);
  const [mode, setMode] = useState<CanvasMode>("markup");
  const { listing, image, error, startNew, select, refresh } = useImages();
  const { shown, before, view } = useViewed(image);
  const runs = useRuns(image);
  // The image a dialog is asking about, by its name.
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const dataDirectory = listing?.data_directory ?? null;
  useEffect(() => followDirectory(dataDirectory), [dataDirectory]);
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
    if (image) {
      setMode(picked);
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
    onRename: setRenaming,
    onDelete: setDeleting,
  };
  const canvas = (
    <Canvas
      listing={listing}
      image={image}
      shown={shown}
      before={before}
      runs={runs}
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
        display.fullscreen ? "h-dvh" : "h-[560px]",
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
            value={image ? mode : null}
            onChange={pickMode}
            options={[
              {
                value: "markup",
                label: "Markup",
                icon: "mark",
                disabled: image ? undefined : NEEDS_SOURCE,
              },
              {
                value: "mask",
                label: "Mask",
                icon: "area",
                disabled: image ? undefined : NEEDS_SOURCE,
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
      <RenameDialog
        name={renaming}
        onClose={() => setRenaming(null)}
        onRenamed={(name) => {
          // Only the image in view takes the view with it; another one renamed from the list stays out of it.
          if (renaming === image?.name) {
            select(name);
          }
          if (renaming !== null) {
            moveDraft(renaming, name);
          }
          void refresh();
        }}
      />
      <DeleteDialog
        name={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={() => void refresh()}
      />
    </div>
  );
}

export default App;
