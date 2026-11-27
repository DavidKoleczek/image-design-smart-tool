import { useRef } from "react";

import { Icon } from "@/components/ui/icon";
import { Notice } from "@/components/ui/notice";
import { Tooltip } from "@/components/ui/tooltip";
import type { ImageMethods } from "@/lib/api";
import { changeConfig, imageModelOrder, useConfig } from "@/lib/config";
import { moved, useReorder } from "@/lib/reorder";
import { CHATGPT, imageModelLabel } from "@/lib/request";
import { cn } from "@/lib/utils";

/**
 * The order the image's agent is given an image model in when none is picked, here and by any agent that asks it for
 * an image, which the person drags to change. The first that is set up is the one it gets.
 */
export function ImageModelOrder({ methods }: { methods: ImageMethods }) {
  const { config, error } = useConfig();
  const list = useRef<HTMLOListElement>(null);
  const order = imageModelOrder(config, methods);
  const methodOf = (model: string) =>
    model === CHATGPT ? methods.chatgpt : methods.openai;
  const first = order.find((model) => methodOf(model).ready) ?? null;
  const move = (model: string, index: number) =>
    changeConfig((current) => {
      const now = imageModelOrder(current, methods);
      return {
        ...current,
        design_image_models: moved(now, now.indexOf(model), index),
      };
    });
  const reorder = useReorder(list, false, move);

  return (
    <>
      <ol ref={list} className="flex flex-col">
        {order.map((model, index) => {
          const label = imageModelLabel(model, methods);
          return (
            <li
              key={model}
              className={cn(
                "group flex h-7 items-center gap-1.5 rounded-sm pr-1",
                reorder.dragging === model && "bg-accent-soft",
              )}
            >
              <Tooltip content="Drag to reorder" side="left">
                <button
                  type="button"
                  aria-label={`Reorder ${label}`}
                  onPointerDown={(event) => reorder.start(model, event)}
                  onKeyDown={(event) => {
                    const way =
                      event.key === "ArrowUp"
                        ? -1
                        : event.key === "ArrowDown"
                          ? 1
                          : 0;
                    if (way) {
                      event.preventDefault();
                      move(model, index + way);
                    }
                  }}
                  className="grid h-6 w-4 shrink-0 cursor-grab touch-none place-items-center rounded-sm text-ink-faint group-hover:text-ink-muted focus-visible:focus-ring focus-visible:outline-none"
                >
                  <Icon name="grip" />
                </button>
              </Tooltip>
              <span className="w-3 shrink-0 mono-annotation text-ink-muted">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 truncate">{label}</span>
              {model === first ? (
                <span className="shrink-0 mono-annotation text-accent-ink">
                  Default
                </span>
              ) : (
                !methodOf(model).ready && (
                  <span
                    title={methodOf(model).problem ?? undefined}
                    className="shrink-0 mono-annotation text-ink-muted"
                  >
                    Not set up
                  </span>
                )
              )}
            </li>
          );
        })}
      </ol>
      {error && <Notice className="mt-1.5">{error}</Notice>}
    </>
  );
}
