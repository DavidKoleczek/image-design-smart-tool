import { useState, type ReactNode } from "react";

import { SettingsMenu } from "@/components/SettingsMenu";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip } from "@/components/ui/tooltip";
import { AppMark, Wordmark } from "@/components/Wordmark";
import { WorkspacePicker } from "@/components/WorkspacePicker";
import type { ImageSummary } from "@/lib/api";
import type { Breakpoint } from "@/lib/layout";
import { folderName, refreshWorkspaces, useWorkspaces } from "@/lib/workspaces";

export type Pane = "images" | "request";
export type NarrowPane = "image" | "request";

const PANE_LABELS: Record<Pane, string> = {
  images: "Your images",
  request: "Request",
};

function Divider() {
  return <span aria-hidden className="mx-1 h-5 w-px shrink-0 bg-line" />;
}

/** The workspace the app shows, by its folder's name, opening the workspaces to switch to; its icon alone when narrow. */
function WorkspaceSwitcher({ compact }: { compact: boolean }) {
  const { shown } = useWorkspaces();
  const [open, setOpen] = useState(false);
  const name = shown === null ? "Workspace" : folderName(shown);
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        // Another app may have opened, or a folder gone, since they were read.
        if (next) {
          void refreshWorkspaces();
        }
      }}
    >
      <Tooltip content={shown ?? "Workspace"}>
        <PopoverTrigger
          render={
            <Button
              size="sm"
              icon={compact}
              aria-label={`Workspace: ${name}`}
              className={compact ? undefined : "min-w-0 shrink"}
            />
          }
        >
          <Icon name="folder" />
          {!compact && (
            <>
              <span className="min-w-0 truncate text-body font-medium">
                {name}
              </span>
              <Icon name="chevron" className="text-ink-muted" />
            </>
          )}
        </PopoverTrigger>
      </Tooltip>
      <PopoverContent
        label="Workspaces"
        align="start"
        className="w-90 max-w-[calc(100vw-16px)]"
      >
        <p className="px-2 pt-1 pb-1.5 text-label text-ink-muted">Workspaces</p>
        <WorkspacePicker onPicked={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
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

/** The bar along the top: the brand, the workspace, the path of the image in view, and the app's controls. */
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
      <WorkspaceSwitcher compact={breakpoint === "narrow"} />
      <span aria-hidden className="shrink-0 text-ink-faint">
        /
      </span>
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
