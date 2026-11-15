import {
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import {
  Group,
  Panel,
  useGroupRef,
  type Layout,
  type PanelImperativeHandle,
} from "react-resizable-panels";

import { ResizeHandle } from "@/components/ui/resizable";
import type { AppLayout, PaneLayout } from "@/lib/api";

const IMAGES = { min: 200, default: 272 };
const TABS_MIN = 360;
const CANVAS_MIN = 360;
const REQUEST_WIDE = { min: 340, default: 408 };
const REQUEST_MEDIUM = { min: 300, default: 0.42 };

/** A side pane's width in pixels as the person left it, 0 when closed. */
function pixels(pane: PaneLayout, fallback: number): number {
  return pane.open ? (pane.size ?? fallback) : 0;
}

/** Where Your images and the tabs start, as percentages of the width the workspace has now. */
function imagesLayout(layout: AppLayout, width: number): Layout | undefined {
  if (width <= 0) {
    return undefined;
  }
  const images = (pixels(layout.images, IMAGES.default) / width) * 100;
  return { images, tabs: 100 - images };
}

/** Where the canvas and Request start, as percentages of the width a tab has now. */
function requestLayout(
  wide: boolean,
  layout: AppLayout,
  width: number,
): Layout | undefined {
  if (width <= 0) {
    return undefined;
  }
  const request =
    (pixels(
      layout.request,
      wide ? REQUEST_WIDE.default : REQUEST_MEDIUM.default * width,
    ) /
      width) *
    100;
  return { canvas: 100 - request, request };
}

/** How wide the tabs are at first, before they can be measured: the view, less Your images where it shows. */
function tabsWidth(wide: boolean, layout: AppLayout, width: number): number {
  return wide ? width - pixels(layout.images, IMAGES.default) : width;
}

/**
 * Your images beside the tabs, resizable and collapsible. A side pane opens as far as the person drags it, up to what
 * leaves the tabs 360px.
 */
export function Workspace({
  layout,
  width,
  images,
  imagesPanel,
  tabs,
  onChanged,
}: {
  layout: AppLayout;
  width: number;
  images: ReactNode;
  imagesPanel: RefObject<PanelImperativeHandle | null>;
  tabs: ReactNode;
  /** Your images' width in pixels after a change, 0 when closed, and whether the person made the change. */
  onChanged: (width: number, user: boolean) => void;
}) {
  // Read once: the group takes its layout from here only as it mounts.
  const [start] = useState(() => imagesLayout(layout, width));
  const group = useGroupRef();
  const element = useRef<HTMLDivElement>(null);
  // As the layout is reset, which the tabs in it outlive.
  useLayoutEffect(() => {
    const wanted = imagesLayout(layout, element.current?.offsetWidth ?? 0);
    if (wanted) {
      group.current?.setLayout(wanted);
    }
  }, [layout, group]);
  return (
    <Group
      orientation="horizontal"
      defaultLayout={start}
      groupRef={group}
      elementRef={element}
      onLayoutChanged={(changed, meta) =>
        onChanged(
          Math.round(
            ((changed.images ?? 0) / 100) * (element.current?.offsetWidth ?? 0),
          ),
          meta.isUserInteraction,
        )
      }
      className="min-h-0 flex-1"
    >
      <Panel
        id="images"
        panelRef={imagesPanel}
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
      <Panel id="tabs" minSize={TABS_MIN} className="h-full">
        {tabs}
      </Panel>
    </Group>
  );
}

/**
 * A tab's canvas beside Request, which is resizable and collapsible. Request is as wide in every tab, so a tab that
 * comes into view takes the width it was given in another.
 */
export function TabPanes({
  wide,
  layout,
  width,
  active,
  requestPanel,
  canvas,
  request,
  onChanged,
}: {
  wide: boolean;
  layout: AppLayout;
  /** The view's width. */
  width: number;
  /** Whether the tab is in view. */
  active: boolean;
  /** Request's panel, for the tab in view. */
  requestPanel: RefObject<PanelImperativeHandle | null> | undefined;
  canvas: ReactNode;
  request: ReactNode;
  /** Request's width in pixels after a change, 0 when closed, and whether the person made the change. */
  onChanged: (width: number, user: boolean) => void;
}) {
  // Read once: the group takes its layout from here only as it mounts.
  const [start] = useState(() =>
    requestLayout(wide, layout, tabsWidth(wide, layout, width)),
  );
  const group = useGroupRef();
  const element = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!active) {
      return;
    }
    const wanted = requestLayout(
      wide,
      layout,
      element.current?.offsetWidth ?? 0,
    );
    if (wanted) {
      group.current?.setLayout(wanted);
    }
  }, [active, wide, layout, group]);
  return (
    <Group
      orientation="horizontal"
      defaultLayout={start}
      groupRef={group}
      elementRef={element}
      onLayoutChanged={(changed, meta) => {
        if (active) {
          onChanged(
            Math.round(
              ((changed.request ?? 0) / 100) *
                (element.current?.offsetWidth ?? 0),
            ),
            meta.isUserInteraction,
          );
        }
      }}
      className="min-h-0 flex-1"
    >
      <Panel id="canvas" minSize={CANVAS_MIN} className="h-full">
        {canvas}
      </Panel>
      <ResizeHandle label="Resize Request" />
      <Panel
        id="request"
        panelRef={requestPanel}
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
