import type { ReactNode } from "react";

import { SettingsMenu } from "@/components/SettingsMenu";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip } from "@/components/ui/tooltip";
import { AppMark, Wordmark } from "@/components/Wordmark";
import type { ImageSummary } from "@/lib/api";
import type { Breakpoint } from "@/lib/layout";

export type Pane = "images" | "request";
export type NarrowPane = "image" | "request";

const PANE_LABELS: Record<Pane, string> = {
  images: "Your images",
  request: "Request",
};

function Divider() {
  return <span aria-hidden className="mx-1 h-5 w-px shrink-0 bg-line" />;
}

function PaneToggle({
  pane,
  open,
  onToggle,
}: {
  pane: Pane;
  open: boolean;
  onToggle: (pane: Pane) => void;
}) {
  const label = PANE_LABELS[pane];
  return (
    <Tooltip content={label} keys={pane === "images" ? "[" : "]"}>
      <Button
        size="sm"
        icon
        aria-label={label}
        aria-pressed={open}
        onClick={() => onToggle(pane)}
      >
        <Icon name={pane === "images" ? "sidebar-left" : "sidebar-right"} />
      </Button>
    </Tooltip>
  );
}

/** The bar along the top: the brand, the path of the image in view, and the app's controls. */
export function TopBar({
  breakpoint,
  image,
  switcher,
  center,
  panes,
  onTogglePane,
  narrowPane,
  onNarrowPane,
  onNew,
  onExpand,
  onShortcuts,
}: {
  breakpoint: Breakpoint;
  /** The image in view; none for a new image, not generated yet. */
  image: ImageSummary | null;
  /** Picks the image in view, where Your images has no room; it then stands where the image's name does. */
  switcher: ReactNode;
  center?: ReactNode;
  panes: Record<Pane, boolean>;
  onTogglePane: (pane: Pane) => void;
  narrowPane: NarrowPane;
  onNarrowPane: (pane: NarrowPane) => void;
  onNew: () => void;
  /** Asks the host for fullscreen; absent when the view is fullscreen already, or the host has no such mode. */
  onExpand?: () => void;
  onShortcuts: () => void;
}) {
  return (
    <header className="flex h-11 shrink-0 items-center gap-2 border-b border-line bg-panel pr-2 pl-3">
      {breakpoint === "narrow" ? (
        <AppMark />
      ) : (
        <h1 className="flex shrink-0 items-center">
          <Wordmark />
        </h1>
      )}
      {breakpoint !== "narrow" && <Divider />}
      {breakpoint === "wide" ? (
        <span className="min-w-0 truncate font-medium">
          {image ? image.name : "New image"}
        </span>
      ) : (
        switcher
      )}
      <span className="flex-1" />
      {breakpoint !== "narrow" && center}
      {breakpoint === "wide" && <span className="flex-1" />}
      {breakpoint === "narrow" && (
        <Segmented
          label="Show"
          size="sm"
          value={narrowPane}
          onChange={onNarrowPane}
          options={[
            { value: "image", label: "Image" },
            { value: "request", label: "Request" },
          ]}
        />
      )}
      {/* Your images has the button beside its search field while it shows. */}
      {breakpoint === "wide" && !panes.images ? (
        <Button variant="secondary" size="sm" onClick={onNew}>
          <Icon name="add" />
          New image
        </Button>
      ) : (
        breakpoint !== "wide" && (
          <Tooltip content="New image" keys="N">
            <Button size="sm" icon aria-label="New image" onClick={onNew}>
              <Icon name="add" />
            </Button>
          </Tooltip>
        )
      )}
      {breakpoint === "wide" && <Divider />}
      {breakpoint === "wide" && (
        <PaneToggle pane="images" open={panes.images} onToggle={onTogglePane} />
      )}
      {breakpoint !== "narrow" && (
        <PaneToggle
          pane="request"
          open={panes.request}
          onToggle={onTogglePane}
        />
      )}
      <SettingsMenu onShortcuts={onShortcuts} />
      {onExpand && (
        <Tooltip content="Expand">
          <Button size="sm" icon aria-label="Expand" onClick={onExpand}>
            <Icon name="expand" />
          </Button>
        </Tooltip>
      )}
    </header>
  );
}
