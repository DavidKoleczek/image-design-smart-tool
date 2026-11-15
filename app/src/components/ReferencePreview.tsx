import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Tooltip } from "@/components/ui/tooltip";
import { readReferenceFile, type ReferenceEntry } from "@/lib/api";
import { describe } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { togglePin } from "@/lib/references";
import { useAppState } from "@/lib/state";

/** The reference at `path` as a request sends it, as a data URL, once it is read. */
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

function Large({ entry }: { entry: ReferenceEntry }) {
  const { url, error } = useLarge(entry.path);
  return (
    <div className="absolute inset-x-14 inset-y-4 flex items-center justify-center">
      {url ? (
        <img
          src={url}
          alt={entry.name}
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

/**
 * A reference shown large, as a request sends it, to look at before adding it. The arrow keys and the buttons at its
 * sides step through what the library shows, in the order it shows it.
 */
export function ReferencePreview({
  entries,
  path,
  onShow,
  picked,
  blocked,
  onToggle,
}: {
  /** What the library shows, in the order it shows it. */
  entries: ReferenceEntry[];
  /** The one shown large; null while none is. */
  path: string | null;
  onShow: (path: string | null) => void;
  picked: (entry: ReferenceEntry) => boolean;
  /** Why it cannot be added now; null when it can. */
  blocked: (entry: ReferenceEntry) => string | null;
  onToggle: (entry: ReferenceEntry) => void;
}) {
  const { state } = useAppState();
  const index = entries.findIndex((entry) => entry.path === path);
  const showing = index >= 0 ? entries[index] : null;
  // The last one shown stays while the dialog closes, so it fades out with it.
  const [held, setHeld] = useState(showing);
  if (showing !== null && showing.path !== held?.path) {
    setHeld(showing);
  }
  const entry = showing ?? held;
  const before = index > 0 ? entries[index - 1] : null;
  const after = index >= 0 ? (entries[index + 1] ?? null) : null;

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

  if (entry === null) {
    return null;
  }
  const isPicked = picked(entry);
  const reason = isPicked ? null : blocked(entry);
  const pinned = state.pins.includes(entry.path);
  return (
    <Dialog
      open={showing !== null}
      onOpenChange={(open) => !open && onShow(null)}
    >
      <DialogContent
        title={entry.name}
        subtitle={entry.path}
        className="sm:h-full sm:max-w-400"
      >
        <div className="relative min-h-64 flex-1 bg-field">
          <Large key={entry.path} entry={entry} />
          {entries.length > 1 && (
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
        <DialogFooter>
          <span className="mono-annotation text-ink-muted">
            {index >= 0 && `${index + 1} of ${entries.length}`}
          </span>
          {entry.width !== null && entry.height !== null && (
            <span className="mono-annotation text-ink-muted">
              {dimensions(entry.width, entry.height)}
            </span>
          )}
          <span className="min-w-0 flex-1 truncate text-right text-caption text-ink-muted">
            {reason}
          </span>
          <Button
            variant="secondary"
            aria-pressed={pinned}
            onClick={() => togglePin(entry.path)}
          >
            <Icon name={pinned ? "pinned" : "pin"} />
            {pinned ? "Unpin" : "Pin"}
          </Button>
          <Button
            variant={isPicked ? "secondary" : "primary"}
            disabled={reason !== null}
            onClick={() => onToggle(entry)}
          >
            <Icon name={isPicked ? "close" : "add"} />
            {isPicked ? "Remove" : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
