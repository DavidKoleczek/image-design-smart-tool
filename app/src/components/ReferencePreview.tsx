import { ImageViewer } from "@/components/ImageViewer";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import type { ReferenceEntry } from "@/lib/api";
import { dimensions } from "@/lib/format";
import { togglePin } from "@/lib/references";
import { useAppState } from "@/lib/state";

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
  return (
    <ImageViewer
      items={entries}
      path={path}
      onShow={onShow}
      footer={(entry, index) => {
        const isPicked = picked(entry);
        const reason = isPicked ? null : blocked(entry);
        const pinned = state.pins.includes(entry.path);
        return (
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
        );
      }}
    />
  );
}
