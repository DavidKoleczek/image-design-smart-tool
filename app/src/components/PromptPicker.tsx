import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { EarlierPrompt } from "@/lib/prompts";
import { ago } from "@/lib/time";
import { cn } from "@/lib/utils";

/** Fills the prompt from an earlier one, in place of what is written. */
export function PromptPicker({
  editing,
  prompts,
  current,
  onPick,
}: {
  /** Whether the request changes an image, whose versions the prompts come from, rather than making a new one. */
  editing: boolean;
  prompts: EarlierPrompt[];
  current: string;
  onPick: (prompt: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            size="sm"
            disabled={prompts.length === 0}
            title={prompts.length === 0 ? "No earlier prompts yet" : undefined}
          />
        }
      >
        <Icon name="clock" />
        {editing ? "Load from version" : "Load from image"}
      </PopoverTrigger>
      <PopoverContent
        label="Earlier prompts"
        className="flex max-h-[min(420px,70vh)] w-89 flex-col overflow-y-auto"
      >
        {prompts.map((prompt) => (
          <button
            key={prompt.key}
            type="button"
            onClick={() => {
              onPick(prompt.text);
              setOpen(false);
            }}
            className={cn(
              "flex shrink-0 cursor-default flex-col gap-1 rounded-sm px-2 py-1.5 text-left outline-none hover:bg-hover focus-visible:bg-hover",
              prompt.text === current && "bg-accent-soft",
            )}
          >
            <span className="flex min-w-0 items-center gap-2 mono-annotation">
              <span className="truncate text-ink">{prompt.tag}</span>
              <span className="shrink-0 text-ink-muted">
                {ago(prompt.when)}
              </span>
            </span>
            <span className="line-clamp-2 text-label font-normal">
              {prompt.text}
            </span>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}
