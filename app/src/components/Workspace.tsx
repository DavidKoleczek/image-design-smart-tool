import { useRef, useState, type ReactNode, type RefObject } from "react";
import {
  Group,
  Panel,
  type Layout,
  type PanelImperativeHandle,
} from "react-resizable-panels";

import { ResizeHandle } from "@/components/ui/resizable";
import type { AppLayout, PaneLayout } from "@/lib/api";

const IMAGES = { min: 200, default: 272 };
const CANVAS_MIN = 360;
const REQUEST_WIDE = { min: 340, default: 408 };
const REQUEST_MEDIUM = { min: 300, default: 0.42 };

export type PaneRefs = {
  images: RefObject<PanelImperativeHandle | null>;
  request: RefObject<PanelImperativeHandle | null>;
};

/** Where the panes start: as the person left them, as percentages of the width the workspace has now. */
function startingLayout(
  wide: boolean,
  layout: AppLayout,
  width: number,
): Layout | undefined {
  if (width <= 0) {
    return undefined;
  }
  const pixels = (pane: PaneLayout, fallback: number) =>
    pane.open ? (pane.size ?? fallback) : 0;
  const share = (size: number) => (size / width) * 100;
  const request = share(
    pixels(
      layout.request,
      wide ? REQUEST_WIDE.default : REQUEST_MEDIUM.default * width,
    ),
  );
  const images = wide ? share(pixels(layout.images, IMAGES.default)) : 0;
  return wide
    ? { images, canvas: 100 - images - request, request }
    : { canvas: 100 - request, request };
}

/**
 * The canvas between Your images and Request, each resizable and collapsible; at medium widths, the canvas and
 * Request alone. A side pane opens as far as the person drags it, up to what leaves the canvas 360px.
 */
export function Workspace({
  wide,
  layout,
  width,
  panes,
  images,
  canvas,
  request,
  onChanged,
}: {
  wide: boolean;
  layout: AppLayout;
  width: number;
  panes: PaneRefs;
  images: ReactNode;
  canvas: ReactNode;
  request: ReactNode;
  /** Each side pane's width in pixels after a change, 0 when closed, and whether the person made the change. */
  onChanged: (
    widths: Record<"images" | "request", number>,
    user: boolean,
  ) => void;
}) {
  // Read once: the group takes its layout from here only as it mounts.
  const [start] = useState(() => startingLayout(wide, layout, width));
  const group = useRef<HTMLDivElement>(null);
  return (
    <Group
      orientation="horizontal"
      defaultLayout={start}
      elementRef={group}
      onLayoutChanged={(changed, meta) => {
        const room = group.current?.offsetWidth ?? 0;
        const pixels = (id: string) =>
          Math.round(((changed[id] ?? 0) / 100) * room);
        onChanged(
          { images: pixels("images"), request: pixels("request") },
          meta.isUserInteraction,
        );
      }}
      className="min-h-0 flex-1"
    >
      {wide && (
        <>
          <Panel
            id="images"
            panelRef={panes.images}
            collapsible
            collapsedSize={0}
            minSize={IMAGES.min}
            defaultSize={IMAGES.default}
            groupResizeBehavior="preserve-pixel-size"
            className="h-full"
          >
            {images}
          </Panel>
          <ResizeHandle label="Resize Your images" />
        </>
      )}
      <Panel id="canvas" minSize={CANVAS_MIN} className="h-full">
        {canvas}
      </Panel>
      <ResizeHandle label="Resize Request" />
      <Panel
        id="request"
        panelRef={panes.request}
        collapsible
        collapsedSize={0}
        minSize={wide ? REQUEST_WIDE.min : REQUEST_MEDIUM.min}
        defaultSize={
          wide ? REQUEST_WIDE.default : `${REQUEST_MEDIUM.default * 100}%`
        }
        groupResizeBehavior={wide ? "preserve-pixel-size" : undefined}
        className="h-full"
      >
        {request}
      </Panel>
    </Group>
  );
}
