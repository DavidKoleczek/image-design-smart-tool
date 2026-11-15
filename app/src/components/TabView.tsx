import { Activity, useEffect, type RefObject } from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";

import { Canvas } from "@/components/Canvas";
import { RequestPane } from "@/components/RequestPane";
import type { NarrowPane } from "@/components/TopBar";
import { TabPanes } from "@/components/Workspace";
import type { AppLayout, AppMethod, ImageListing } from "@/lib/api";
import { useGuides } from "@/lib/canvas";
import { useDraft } from "@/lib/drafts";
import { useGuidance } from "@/lib/guidance";
import { useReferences } from "@/lib/references";
import { useRuns } from "@/lib/runs";
import { updateAppState } from "@/lib/state";
import {
  createdIn,
  keepTab,
  keyOf,
  openImage,
  tabPanelId,
  updateTab,
  type Tab,
} from "@/lib/tabs";
import { viewed } from "@/lib/viewed";

/**
 * What one tab shows: its image on the canvas beside its request, or at narrow widths one of them. It stays mounted
 * while another tab is in view, hidden, so everything in it is as it was when it comes back.
 */
export function TabView({
  tab,
  active,
  listing,
  error,
  wide,
  narrow,
  layout,
  width,
  requestPanel,
  onLayout,
  onUseInNew,
  onRefresh,
}: {
  tab: Tab;
  /** Whether the tab is in view. */
  active: boolean;
  listing: ImageListing | null;
  /** Why the images could not be listed. */
  error: string | null;
  wide: boolean;
  /** At narrow widths, which of the canvas and the request shows; null where both do. */
  narrow: NarrowPane | null;
  layout: AppLayout;
  width: number;
  /** Request's panel, when the tab is in view. */
  requestPanel: RefObject<PanelImperativeHandle | null>;
  /** Request's width after a change, and whether the person made the change. */
  onLayout: (width: number, user: boolean) => void;
  /** Start a new image with the image named as its first reference. */
  onUseInNew: (name: string) => void;
  /** List the images now, as after a change made here. */
  onRefresh: () => Promise<void>;
}) {
  const key = keyOf(tab);
  const image =
    tab.image === null
      ? null
      : (listing?.images.find((each) => each.name === tab.image) ?? null);
  const { shown, before } = viewed(image, tab.version);
  const runs = useRuns(image);
  const { blocks, mode, steering } = useGuidance(tab, image, shown);
  const draft = useDraft(key);
  const references = useReferences(key);
  const guides = useGuides(key, shown?.picture?.key ?? null);
  // Something done in a preview tab keeps it from being taken by the next image opened.
  const worked =
    draft.prompt.trim() !== "" ||
    guides.marks.length > 0 ||
    guides.painted > 0 ||
    references.length > 0 ||
    tab.version !== null;
  useEffect(() => {
    if (tab.preview && worked) {
      keepTab(tab.id);
    }
  }, [tab.id, tab.preview, worked]);

  const view = (version: string | null) => updateTab(tab.id, { version });
  const changed = async () => {
    keepTab(tab.id);
    await onRefresh();
  };
  const pickMethod = (method: AppMethod) => {
    updateTab(tab.id, { method });
    keepTab(tab.id);
    // What a new image is made with is what the next one starts on.
    if (tab.image === null) {
      updateAppState((current) => ({ ...current, method }));
    }
  };

  // The image a tab shows is listed once it was made or brought up, so until then there is nothing to show.
  const missing = tab.image !== null && image === null;
  const canvas = (
    <Canvas
      listing={missing ? null : listing}
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
      onChanged={changed}
    />
  );
  const request = missing ? (
    <div className="h-full bg-panel" />
  ) : (
    <RequestPane
      listing={listing}
      image={image}
      shown={shown}
      runs={runs}
      mode={mode}
      newKey={key}
      method={tab.method}
      onMethod={pickMethod}
      onUseInNew={onUseInNew}
      onCreated={async (name) => {
        // Listed first, so the image is there to show.
        await onRefresh();
        if (tab.image === null) {
          createdIn(tab.id, name);
        } else {
          openImage(name, "keep");
        }
      }}
      onChanged={changed}
      onView={view}
    />
  );

  return (
    <div
      role="tabpanel"
      id={tabPanelId(tab)}
      aria-labelledby={`tab-${tab.id}`}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      {narrow !== null ? (
        <>
          <Activity mode={narrow === "image" ? "visible" : "hidden"}>
            {canvas}
          </Activity>
          <Activity mode={narrow === "request" ? "visible" : "hidden"}>
            {request}
          </Activity>
        </>
      ) : (
        <TabPanes
          wide={wide}
          layout={layout}
          width={width}
          active={active}
          requestPanel={active ? requestPanel : undefined}
          canvas={canvas}
          request={request}
          onChanged={onLayout}
        />
      )}
    </div>
  );
}
