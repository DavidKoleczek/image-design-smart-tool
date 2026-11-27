import { useEffect, useState, type ReactNode } from "react";

import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Tooltip } from "@/components/ui/tooltip";
import { readReferenceFile } from "@/lib/api";
import { describe } from "@/lib/errors";

/** An image to show large: its path on the machine the app runs on, as the app offers it, and what it is called. */
export type Viewed = { path: string; name: string };

/** The image at `path` as a request sends it, as a data URL, once it is read. */
function useLarge(path: string): { url: string | null; error: string | null } {
  const [read, setRead] = useState<{
    path: string;
    url: string | null;
    error: string | null;
  } | null>(null);
  useEffect(() => {
    let current = true;
    readReferenceFile(path).then(
      (url) => current && setRead({ path, url, error: null }),
      (cause: unknown) =>
        current && setRead({ path, url: null, error: describe(cause) }),
    );
    return () => {
      current = false;
    };
  }, [path]);
  return read && read.path === path
    ? { url: read.url, error: read.error }
    : { url: null, error: null };
}

/** An image the app offers or keeps, by its path, shown as large as the box it fills. */
function LargeImage({ path, name }: { path: string; name: string }) {
  const { url, error } = useLarge(path);
  return (
    <div className="absolute inset-x-14 inset-y-4 flex items-center justify-center">
      {url ? (
        <img
          src={url}
          alt={name}
          draggable={false}
          className="max-h-full max-w-full checker"
        />
      ) : error ? (
        <p className="max-w-120 text-center text-caption text-ink-muted">
          {error}
        </p>
      ) : (
        <LoadingMark size={24} />
      )}
    </div>
  );
}

/** A small preview of an image, by its path, that shows it large once clicked. */
export function ExpandableThumb({
  path,
  label,
  onExpand,
  className,
  children,
}: {
  path: string;
  /** What it is, for its tooltip and the button's name. */
  label: string;
  onExpand: () => void;
  /** The preview's size. */
  className?: string;
  /** What shows over the preview, such as its number. */
  children?: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={`Show ${label} large`}
      onClick={onExpand}
      // Clickable inside a card whose content lets clicks through to the card.
      className="pointer-events-auto relative block shrink-0 cursor-zoom-in rounded-sm focus-visible:focus-ring focus-visible:outline-none"
    >
      <ReferenceThumb reference={{ path }} className={className} />
      {children}
    </button>
  );
}

/**
 * Images shown large one at a time, as a request sends them. The arrow keys and the buttons at its sides step through
 * them in order.
 */
export function ImageViewer<Item extends Viewed>({
  items,
  path,
  onShow,
  footer,
}: {
  items: Item[];
  /** The one shown large; null while none is. */
  path: string | null;
  onShow: (path: string | null) => void;
  /** What shows under it, given the one shown and where it is among them; by default where it is, among several. */
  footer?: (item: Item, index: number) => ReactNode;
}) {
  const index = items.findIndex((item) => item.path === path);
  const showing = index >= 0 ? items[index] : null;
  // The last one shown stays while the dialog closes, so it fades out with it.
  const [held, setHeld] = useState(showing);
  if (showing !== null && showing.path !== held?.path) {
    setHeld(showing);
  }
  const item = showing ?? held;
  const before = index > 0 ? items[index - 1] : null;
  const after = index >= 0 ? (items[index + 1] ?? null) : null;

  useEffect(() => {
    if (path === null) {
      return;
    }
    const step = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) {
        return;
      }
      const to =
        event.key === "ArrowLeft"
          ? before
          : event.key === "ArrowRight"
            ? after
            : null;
      if (to) {
        event.preventDefault();
        onShow(to.path);
      }
    };
    // On the way down, since a dialog keeps the arrow keys from bubbling out of it.
    window.addEventListener("keydown", step, true);
    return () => window.removeEventListener("keydown", step, true);
  }, [path, before, after, onShow]);

  if (item === null) {
    return null;
  }
  return (
    <Dialog
      open={showing !== null}
      onOpenChange={(open) => !open && onShow(null)}
    >
      <DialogContent
        title={item.name}
        subtitle={item.path}
        className="sm:h-full sm:max-w-400"
      >
        <div className="relative min-h-64 flex-1 bg-field">
          <LargeImage key={item.path} path={item.path} name={item.name} />
          {items.length > 1 && (
            <>
              <Tooltip content="Previous" keys="Left" side="right">
                <Button
                  variant="secondary"
                  icon
                  aria-label="Previous"
                  disabled={before === null}
                  onClick={() => before && onShow(before.path)}
                  className="absolute top-1/2 left-3 -translate-y-1/2"
                >
                  <Icon name="chevron" className="rotate-90" />
                </Button>
              </Tooltip>
              <Tooltip content="Next" keys="Right" side="left">
                <Button
                  variant="secondary"
                  icon
                  aria-label="Next"
                  disabled={after === null}
                  onClick={() => after && onShow(after.path)}
                  className="absolute top-1/2 right-3 -translate-y-1/2"
                >
                  <Icon name="chevron" className="-rotate-90" />
                </Button>
              </Tooltip>
            </>
          )}
        </div>
        {footer
          ? footer(item, index)
          : items.length > 1 && (
              <DialogFooter>
                <span className="mono-annotation text-ink-muted">
                  {index >= 0 && `${index + 1} of ${items.length}`}
                </span>
              </DialogFooter>
            )}
      </DialogContent>
    </Dialog>
  );
}
