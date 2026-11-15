import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { NameField } from "@/components/explorer/NameField";
import { useBox } from "@/components/explorer/useBox";
import { useDrag } from "@/components/explorer/useDrag";
import type { Explorer as Model } from "@/components/explorer/useExplorer";
import { Icon } from "@/components/ui/icon";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "@/components/ui/menu";
import { readDrop } from "@/lib/drops";
import { baseName, folderOf, splitName, within } from "@/lib/paths";
import { boxed, only, stepped } from "@/lib/selection";
import type { Entry, Row } from "@/lib/tree";
import { cn } from "@/lib/utils";

const INDENT = 16;

/** How the files are drawn, each by its path. Folders are drawn the same everywhere. */
export type Drawing = {
  /** A file's small preview, before its name in a row. */
  icon: (path: string) => ReactNode;
  /** What follows a file's name in its row, at the row's far end. */
  detail: (path: string) => ReactNode;
  /** A file's preview in the grid, over its name. */
  tile: (path: string) => ReactNode;
  /** What goes before a file's name in the grid, such as a mark for its status. */
  mark: (path: string) => ReactNode;
  /**
   * The items of the menu a right click opens: on an entry, which is then in the selection, or with null on the
   * space under the entries.
   */
  menu: (entry: Entry | null) => ReactNode;
};

type Pending = {
  folder: string;
  label: string;
  icon: ReactNode;
  tile: ReactNode;
};

/** Where a file not there yet goes among the lines: after everything in its folder, while that folder is open. */
function pendingAt(
  rows: Row[],
  folder: string,
): { at: number; depth: number } | null {
  if (folder === "") {
    return { at: rows.length, depth: 0 };
  }
  const index = rows.findIndex((row) => row.folder && row.path === folder);
  if (index < 0 || !rows[index].open) {
    return null;
  }
  let at = index + 1;
  while (at < rows.length && within(rows[at].path, folder)) {
    at += 1;
  }
  return { at, depth: rows[index].depth + 1 };
}

function itemOf(list: HTMLElement, path: string): HTMLElement | null {
  return list.querySelector(`[data-path="${CSS.escape(path)}"]`);
}

/**
 * The entry above or below another as they are laid out, for the grid, where the next one in order is beside it.
 * It is the nearest line that way, and in that line whatever is closest across.
 */
function beside(list: HTMLElement, path: string, down: boolean): string | null {
  const from = itemOf(list, path)?.getBoundingClientRect();
  if (!from) {
    return null;
  }
  let best: { path: string; away: number; across: number } | null = null;
  for (const each of list.querySelectorAll<HTMLElement>("[data-path]")) {
    const rect = each.getBoundingClientRect();
    const away = down ? rect.top - from.bottom : from.top - rect.bottom;
    if (away < -1) {
      continue;
    }
    const middle = from.left + from.width / 2;
    const across =
      middle < rect.left
        ? rect.left - middle
        : middle > rect.right
          ? middle - rect.right
          : 0;
    if (
      best === null ||
      away < best.away - 1 ||
      (Math.abs(away - best.away) <= 1 && across < best.across)
    ) {
      best = { path: each.dataset.path ?? "", away, across };
    }
  }
  return best?.path ?? null;
}

/**
 * A file tree, as details, one line an entry with folders that open and close, or as a grid of the files under the
 * folder each is in. Clicks, Ctrl and Shift, the arrow keys, and a box drawn from blank space select as in a file
 * manager. A name is typed in place, entries are dragged to another folder or cut, copied, and pasted there, and
 * files are dropped in from outside. `useExplorer` holds what it shows.
 */
export function Explorer({
  explorer,
  label,
  current,
  draw,
  header,
  pending,
  children,
}: {
  explorer: Model;
  /** Names the tree, for a screen reader. */
  label: string;
  /** The file in view, which is marked whether or not it is selected. */
  current: string | null;
  draw: Drawing;
  /** Stays at the top of the details view, over the lines, such as the names of what `detail` shows. */
  header?: ReactNode;
  /**
   * A file that is not there yet, such as a new one being described. It shows last in its folder, "" for the top,
   * while that folder shows: `icon` and `label` as a file's are in a line, and `tile` and `label` in the grid.
   */
  pending?: Pending;
  /** Shows under the entries. */
  children?: ReactNode;
}) {
  const list = useRef<HTMLDivElement>(null);
  const { selection, order, editing, view } = explorer;
  const { box, start, drew } = useBox(list, (adding) => {
    const kept = adding ? selection : null;
    return (touched) => explorer.select(boxed(kept, touched));
  });
  const drag = useDrag(list, {
    take: explorer.take,
    folderAt: explorer.folderAt,
    allows: explorer.allows,
    onHold: explorer.hold,
    onDrop: explorer.putInto,
    onFiles: (transfer, folder) =>
      void readDrop(transfer).then((dropped) =>
        explorer.bring(dropped, folder),
      ),
  });
  const { dragging } = drag;
  // What the menu is about: the entry that was right clicked, or none for the space under the entries.
  const [menuOn, setMenuOn] = useState<Entry | null>(null);
  // The one stop the Tab key makes in the tree: where the keys last were, or the top.
  const stop = selection.lead ?? order[0] ?? null;
  const lead = selection.lead;

  // The keys move the focus with the selection, while the focus is in the tree and not in a name being typed.
  useEffect(() => {
    const element = list.current;
    const focused = document.activeElement;
    if (
      lead !== null &&
      element?.contains(focused) &&
      !(focused instanceof HTMLInputElement)
    ) {
      itemOf(element, lead)?.focus();
    }
  }, [lead]);

  const focusOn = (path: string) =>
    requestAnimationFrame(() => {
      if (list.current) {
        itemOf(list.current, path)?.focus();
      }
    });

  /** The entry an event in the tree is for. One from a menu, which React passes up from outside the tree, has none. */
  const entryOf = (event: MouseEvent | KeyboardEvent): string | null => {
    const target = event.target as HTMLElement;
    return event.currentTarget.contains(target)
      ? (target.closest<HTMLElement>("[data-path]")?.dataset.path ?? null)
      : null;
  };
  const inTree = (event: MouseEvent | KeyboardEvent) =>
    event.currentTarget.contains(event.target as Node) &&
    (event.target as HTMLElement).closest("input") === null;

  const clicked = (event: MouseEvent) => {
    if (!inTree(event) || drew() || drag.dragged()) {
      return;
    }
    const path = entryOf(event);
    if (path === null) {
      explorer.clear();
      list.current?.focus();
    } else if ((event.target as HTMLElement).closest("[data-toggle]")) {
      explorer.toggle(path);
    } else {
      explorer.click(path, {
        toggle: event.ctrlKey || event.metaKey,
        range: event.shiftKey,
      });
    }
  };

  // A double click on a name renames it, as in a file manager. Anywhere else on a file it opens it to stay.
  const doubleClicked = (event: MouseEvent) => {
    const path = entryOf(event);
    if (path === null || !inTree(event)) {
      return;
    }
    if ((event.target as HTMLElement).closest("[data-name]")) {
      explorer.rename(path);
    } else {
      explorer.openTab(path);
    }
  };

  // The middle button opens a file in a tab of its own, as a link opens in a browser, rather than scrolling.
  const middleClicked = (event: MouseEvent) => {
    const path = entryOf(event);
    if (event.button === 1 && path !== null && inTree(event)) {
      explorer.openTab(path);
    }
  };

  const menuOpened = (event: MouseEvent) => {
    // A name being typed keeps the menu a field has, to paste into it.
    if ((event.target as HTMLElement).closest("input") !== null) {
      event.stopPropagation();
      return;
    }
    const row = explorer.row(entryOf(event) ?? "");
    setMenuOn(row ? { path: row.path, folder: row.folder } : null);
    // A right click on an entry outside the selection selects it first, so the menu is about what looks picked.
    if (row && !selection.paths.has(row.path)) {
      explorer.select(only(row.path));
    }
  };

  const keys = (event: KeyboardEvent) => {
    if (!inTree(event) || event.altKey) {
      return;
    }
    const command = event.ctrlKey || event.metaKey;
    const at = lead === null ? undefined : explorer.row(lead);
    const grid = view === "grid";
    const step = (by: number) => stepped(selection, order, by);
    const key = command ? `Mod+${event.key}` : event.key;
    switch (key) {
      case "ArrowDown":
      case "ArrowUp": {
        const down = key === "ArrowDown";
        explorer.go(
          grid && lead !== null && list.current
            ? beside(list.current, lead, down)
            : step(down ? 1 : -1),
          event.shiftKey,
        );
        break;
      }
      case "ArrowRight":
        if (grid) {
          explorer.go(step(1), event.shiftKey);
        } else if (at?.folder && !at.open) {
          explorer.toggle(at.path);
        } else if (at?.folder && folderOf(step(1) ?? "") === at.path) {
          explorer.go(step(1), false);
        }
        break;
      case "ArrowLeft":
        if (grid) {
          explorer.go(step(-1), event.shiftKey);
        } else if (at?.folder && at.open) {
          explorer.toggle(at.path);
        } else if (at && folderOf(at.path) !== "") {
          explorer.go(folderOf(at.path), false);
        }
        break;
      case "Home":
        explorer.go(order[0] ?? null, event.shiftKey);
        break;
      case "End":
        explorer.go(order.at(-1) ?? null, event.shiftKey);
        break;
      case "Enter":
        if (at) {
          explorer.pick(at.path);
          explorer.toggle(at.path);
        }
        break;
      case "Mod+a":
      case "Mod+A":
        explorer.selectAll();
        break;
      case "Mod+x":
      case "Mod+X":
        explorer.clip(true);
        break;
      case "Mod+c":
      case "Mod+C":
        explorer.clip(false);
        break;
      case "Mod+v":
      case "Mod+V":
        explorer.paste();
        break;
      case "Escape":
        if (explorer.uncut()) {
          break;
        }
        if (selection.paths.size === 0) {
          return;
        }
        explorer.clear();
        break;
      case "F2":
        if (lead !== null) {
          explorer.rename(lead);
        }
        break;
      // Keyboards without a Delete key, as on many Macs, delete with Command and Backspace, as Finder does.
      case "Delete":
      case "Mod+Backspace":
        if (event.shiftKey || (command && !event.metaKey)) {
          return;
        }
        explorer.remove();
        break;
      default:
        return;
    }
    event.preventDefault();
  };

  const nameOf = (row: Row) => {
    const name = baseName(row.path);
    if (editing?.path !== row.path) {
      return (
        <span data-name title={row.path} className="min-w-0 truncate">
          {name}
        </span>
      );
    }
    const [stem, extension] = row.folder ? [name, ""] : splitName(name);
    return (
      <NameField
        name={stem}
        extension={extension}
        onKeep={(typed, byKey) => {
          const kept = explorer.keep(typed);
          if (byKey && kept !== null) {
            focusOn(kept);
          }
        }}
        onDrop={(byKey) => {
          explorer.drop();
          if (byKey && editing.kind === "rename") {
            focusOn(row.path);
          }
        }}
      />
    );
  };

  const itemProps = (row: Row) => {
    const selected = selection.paths.has(row.path);
    return {
      props: {
        role: "treeitem",
        "aria-selected": selected,
        "aria-current": row.path === current || undefined,
        "data-path": row.path,
        tabIndex: row.path === stop ? 0 : -1,
      },
      selected,
      naming: editing?.path === row.path,
      // What was cut shows faded until it is pasted.
      cut: explorer.isCut(row.path) && "opacity-50",
      // The folder a drop would land in is outlined.
      target:
        row.folder &&
        dragging?.into === row.path &&
        "ring-1 ring-accent ring-inset",
    };
  };

  const line = (row: Row) => {
    const { props, selected, naming, cut, target } = itemProps(row);
    const viewed = row.path === current;
    return (
      <div
        key={row.path}
        {...props}
        aria-level={row.depth + 1}
        aria-expanded={row.folder ? row.open : undefined}
        style={{ paddingLeft: (row.folder ? 8 : 26) + row.depth * INDENT }}
        className={cn(
          "relative flex h-6.5 scroll-mt-7 items-center gap-2 rounded-sm pr-2 whitespace-nowrap outline-none focus-visible:focus-ring",
          selected ? "bg-accent-soft" : "hover:bg-hover",
          cut,
          target,
        )}
      >
        {viewed && (
          <span className="absolute inset-y-1 left-0 w-0.5 rounded-sm bg-accent" />
        )}
        <span
          data-handle
          className={cn(
            "flex min-w-12 items-center",
            row.folder ? "gap-1" : "gap-2",
            naming && "flex-1",
            viewed && "font-medium",
          )}
        >
          {row.folder ? (
            <>
              <span data-toggle aria-hidden className="-m-1 p-1">
                <Icon
                  name="chevron"
                  className={cn(
                    "text-ink-muted transition-transform",
                    !row.open && "-rotate-90",
                  )}
                />
              </span>
              <Icon name="folder" className="mr-0.5 text-ink-muted" />
            </>
          ) : (
            draw.icon(row.path)
          )}
          {nameOf(row)}
        </span>
        {!naming && (
          <>
            <span className="min-w-0 flex-1" />
            {!row.folder && draw.detail(row.path)}
          </>
        )}
      </div>
    );
  };

  const heading = (row: Row) => {
    const { props, selected, naming, cut, target } = itemProps(row);
    const above = folderOf(row.path);
    return (
      <div
        key={row.path}
        {...props}
        aria-level={1}
        className={cn(
          "mt-1 flex h-7 scroll-mt-1 items-center rounded-sm px-2 mono-annotation whitespace-nowrap text-ink-muted outline-none focus-visible:focus-ring",
          selected ? "bg-accent-soft text-ink" : "hover:bg-hover",
          cut,
          target,
        )}
      >
        <span
          data-handle
          className={cn(
            "flex min-w-12 items-center gap-1.5",
            naming && "flex-1",
          )}
        >
          <Icon name="folder" />
          {above && <span className="-mr-1.5 truncate">{above}/</span>}
          {nameOf(row)}
        </span>
      </div>
    );
  };

  const tile = (row: Row) => {
    const { props, selected, naming, cut } = itemProps(row);
    return (
      <div
        key={row.path}
        {...props}
        aria-level={2}
        data-handle
        className={cn(
          "flex min-w-0 scroll-mt-1 flex-col gap-1 rounded-md p-1 outline-none focus-visible:focus-ring",
          selected ? "bg-accent-soft" : "hover:bg-hover",
          row.path === current && "ring-1 ring-accent ring-inset",
          cut,
        )}
      >
        {draw.tile(row.path)}
        <span className="flex min-w-0 items-center gap-1 text-caption font-medium">
          {!naming && draw.mark(row.path)}
          {nameOf(row)}
        </span>
      </div>
    );
  };

  const waiting = pending && pendingAt(explorer.rows, pending.folder);
  const waitingLine = pending && waiting && (
    <div
      key=":pending"
      role="none"
      style={{ paddingLeft: 26 + waiting.depth * INDENT }}
      className="flex h-6.5 items-center gap-2 rounded-sm bg-accent-soft pr-2 whitespace-nowrap"
    >
      {pending.icon}
      <span className="min-w-10 flex-1 truncate font-medium">
        {pending.label}
      </span>
    </div>
  );
  const waitingTile = pending && (
    <div
      role="none"
      className="flex min-w-0 flex-col gap-1 rounded-md bg-accent-soft p-1"
    >
      {pending.tile}
      <span className="truncate text-caption font-medium">{pending.label}</span>
    </div>
  );

  const carried = dragging?.paths ?? [];
  const one = carried.length === 1 ? explorer.row(carried[0]) : undefined;

  return (
    <ContextMenu>
      <ContextMenuTrigger
        ref={list}
        role="tree"
        aria-label={label}
        aria-multiselectable
        tabIndex={-1}
        onClick={clicked}
        onDoubleClick={doubleClicked}
        onMouseDown={(event) => event.button === 1 && event.preventDefault()}
        onAuxClick={middleClicked}
        onContextMenuCapture={menuOpened}
        onKeyDown={keys}
        onPointerDown={(event) => {
          start(event);
          drag.start(event);
        }}
        onDragOver={(event) => drag.files.onDragOver(event)}
        onDragLeave={(event) => drag.files.onDragLeave(event)}
        onDrop={(event) => drag.files.onDrop(event)}
        className={cn(
          "relative min-h-0 flex-1 overflow-y-auto px-1.5 pb-2 outline-none select-none",
          dragging?.into === "" && "ring-1 ring-accent ring-inset",
        )}
      >
        {view === "details" && header}
        {view === "details" ? (
          <>
            {explorer.rows.slice(0, waiting?.at).map(line)}
            {waitingLine}
            {waiting && explorer.rows.slice(waiting.at).map(line)}
          </>
        ) : (
          explorer.folders.map((folder) => {
            const row = explorer.row(folder.path);
            const here = pending?.folder === folder.path;
            return (
              <div key={folder.path} role="none" data-folder={folder.path}>
                {row && heading(row)}
                {(folder.files.length > 0 || here) && (
                  <div
                    role="none"
                    className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-1.5 p-0.5"
                  >
                    {folder.files.map((path) => {
                      const file = explorer.row(path);
                      return file ? tile(file) : null;
                    })}
                    {here && waitingTile}
                  </div>
                )}
              </div>
            );
          })
        )}
        {children}
        {box && (
          <div
            aria-hidden
            style={box}
            className="pointer-events-none absolute z-10 rounded-[2px] border border-accent bg-accent/15"
          />
        )}
      </ContextMenuTrigger>
      <ContextMenuContent>{draw.menu(menuOn)}</ContextMenuContent>
      {carried.length > 0 &&
        // Over everything, where nothing the tree is in can clip it.
        createPortal(
          <div
            ref={(element) => drag.ghost(element)}
            aria-hidden
            className="pointer-events-none fixed top-0 left-0 z-50 flex h-7 max-w-56 items-center gap-2 rounded-sm border border-line bg-raised px-2 text-body whitespace-nowrap text-ink shadow-popover"
          >
            {dragging?.copy && (
              <Icon name="add" className="size-3 text-accent-ink" />
            )}
            {one ? (
              <>
                {one.folder ? (
                  <Icon name="folder" className="text-ink-muted" />
                ) : (
                  draw.icon(one.path)
                )}
                <span className="min-w-0 truncate">{baseName(one.path)}</span>
              </>
            ) : (
              `${carried.length} items`
            )}
          </div>,
          document.body,
        )}
    </ContextMenu>
  );
}
