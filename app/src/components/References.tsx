import { useRef, useState, type PointerEvent } from "react";

import { ReferenceLibrary } from "@/components/ReferenceLibrary";
import { ReferenceThumb } from "@/components/ReferenceThumb";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Section } from "@/components/ui/section";
import { Tooltip } from "@/components/ui/tooltip";
import type { ImageListing } from "@/lib/api";
import { describe } from "@/lib/errors";
import {
  addFiles,
  imageFiles,
  moveReference,
  removeReference,
  togglePinned,
  type Reference,
} from "@/lib/references";
import { useAppState } from "@/lib/state";
import { cn } from "@/lib/utils";

/**
 * The images the model looks at without editing them, in the order they go out, which is how the prompt names them.
 * They are added from the library, or by dropping image files here.
 */
export function References({
  open,
  onOpenChange,
  target,
  references,
  room,
  full,
  first,
  listing,
  source,
  onError,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What the request's references are kept under: the image's name, or the new image's key. */
  target: string;
  references: Reference[];
  /** How many references the request can take. */
  room: number;
  /** Why it can take no more, once it has that many. */
  full: string | null;
  /** The number the first reference has among the images the request sends. */
  first: number;
  listing: ImageListing | null;
  /** The image the request edits, which is not offered as a reference to itself. */
  source: string | null;
  onError: (error: string) => void;
}) {
  const { state } = useAppState();
  const [picking, setPicking] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const list = useRef<HTMLOListElement>(null);
  const single = references.length < 2;

  // The drag is followed on the window, and the row moves to whichever place the pointer is over.
  const beginDrag =
    (reference: Reference) => (event: PointerEvent<HTMLButtonElement>) => {
      if (single) {
        return;
      }
      event.preventDefault();
      setDragging(reference.id);
      const move = (moved: globalThis.PointerEvent) => {
        const rows = list.current;
        if (!rows || rows.children.length === 0) {
          return;
        }
        const rect = rows.getBoundingClientRect();
        moveReference(
          target,
          reference.id,
          Math.floor(
            (moved.clientY - rect.top) / (rect.height / rows.children.length),
          ),
        );
      };
      const end = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", end);
        window.removeEventListener("pointercancel", end);
        setDragging(null);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", end);
      window.addEventListener("pointercancel", end);
    };

  return (
    <Section
      title="References"
      open={open}
      onOpenChange={onOpenChange}
      aside={
        <Button size="sm" onClick={() => setPicking(true)}>
          <Icon name="add" />
          Add
        </Button>
      }
    >
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          addFiles(target, imageFiles(event.dataTransfer), room);
        }}
        className={cn(
          "rounded-md",
          over &&
            "outline-1 outline-offset-4 outline-accent-ink outline-dashed",
        )}
      >
        {references.length === 0 ? (
          <p className="rounded-md border border-dashed border-line-control p-3 text-center text-caption text-ink-muted">
            Drop images here, or add them from the library.
          </p>
        ) : (
          <ol ref={list} className="-ml-1.5 flex flex-col">
            {references.map((reference, index) => {
              const pinned =
                reference.path !== null && state.pins.includes(reference.path);
              return (
                <li
                  key={reference.id}
                  className={cn(
                    "group flex h-11 items-center gap-2 rounded-sm",
                    dragging === reference.id && "bg-accent-soft",
                  )}
                >
                  <Tooltip content="Drag to reorder" side="left">
                    <button
                      type="button"
                      aria-label={`Reorder ${reference.name}`}
                      aria-disabled={single || undefined}
                      onPointerDown={beginDrag(reference)}
                      onKeyDown={(event) => {
                        const way =
                          event.key === "ArrowUp"
                            ? -1
                            : event.key === "ArrowDown"
                              ? 1
                              : 0;
                        if (way) {
                          event.preventDefault();
                          moveReference(target, reference.id, index + way);
                        }
                      }}
                      className={cn(
                        "-mr-1 grid h-7 w-4 shrink-0 cursor-grab touch-none place-items-center rounded-sm text-ink-faint group-hover:text-ink-muted focus-visible:focus-ring focus-visible:outline-none",
                        single && "invisible",
                      )}
                    >
                      <Icon name="grip" />
                    </button>
                  </Tooltip>
                  <ReferenceThumb reference={reference} className="size-9" />
                  <span
                    title={reference.name}
                    className="min-w-0 flex-1 truncate mono-value"
                  >
                    {reference.name}
                  </span>
                  {reference.state === "uploading" && <LoadingMark size={12} />}
                  {reference.state === "failed" && (
                    <Icon name="warning" className="text-danger" />
                  )}
                  <span className="shrink-0 mono-annotation text-ink-muted">
                    image {index + first}
                  </span>
                  <Tooltip content={pinned ? "Unpin" : "Pin"}>
                    <Button
                      size="sm"
                      icon
                      aria-pressed={pinned}
                      aria-label={
                        pinned
                          ? `Unpin ${reference.name}`
                          : `Pin ${reference.name}`
                      }
                      disabled={reference.state !== "ready"}
                      onClick={() =>
                        void togglePinned(reference).catch((cause: unknown) =>
                          onError(
                            `Could not pin ${reference.name}. ${describe(cause)}`,
                          ),
                        )
                      }
                      className={cn(
                        !pinned &&
                          "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
                      )}
                    >
                      <Icon name={pinned ? "pinned" : "pin"} />
                    </Button>
                  </Tooltip>
                  <Tooltip content="Remove">
                    <Button
                      size="sm"
                      icon
                      aria-label={`Remove ${reference.name}`}
                      onClick={() => removeReference(target, reference.id)}
                    >
                      <Icon name="close" />
                    </Button>
                  </Tooltip>
                </li>
              );
            })}
          </ol>
        )}
      </div>
      <ReferenceLibrary
        open={picking}
        onOpenChange={setPicking}
        target={target}
        references={references}
        room={room}
        full={full}
        listing={listing}
        source={source}
      />
    </Section>
  );
}
