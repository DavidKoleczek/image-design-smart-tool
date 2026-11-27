import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { Message } from "@/components/activity/Message";
import { RunDivider, RunResult } from "@/components/activity/RunParts";
import { StepBlock } from "@/components/activity/StepBlock";
import { Button } from "@/components/ui/button";
import { Dimension } from "@/components/ui/dimension";
import { Icon } from "@/components/ui/icon";
import { Markdown } from "@/components/ui/markdown";
import { Thumb } from "@/components/ui/thumb";
import type { ImageSummary } from "@/lib/api";
import { dimensions } from "@/lib/format";
import { versionPicture } from "@/lib/pictures";
import {
  toggleOpened,
  useOpened,
  type Block,
  type ImageCall,
  type Run,
} from "@/lib/thread";
import { timeOfDay } from "@/lib/time";
import { cn } from "@/lib/utils";

// How close to the bottom still counts as at it, so new entries keep it scrolled down.
const PINNED_PX = 48;
// How long after the person touched the thread a scroll still counts as theirs.
const TOUCHED_MS = 1000;

/** A version a run made, as a card that shows it when clicked: here, or for another image, in that image's tab. */
function Result({
  image,
  version,
  viewing,
  elsewhere,
  onView,
}: {
  image: ImageSummary;
  version: string;
  /** Whether that version is the one that shows. */
  viewing: boolean;
  /** Whether it is of another image than the one whose conversation this is. */
  elsewhere: boolean;
  onView: (version: string) => void;
}) {
  const kept = image.versions.find((each) => each.id === version);
  if (!kept) {
    return null;
  }
  return (
    <li className="shrink-0">
      <button
        type="button"
        aria-label={`${elsewhere ? "Open" : "Show"} ${image.name} ${kept.id}`}
        aria-current={viewing || undefined}
        onClick={() => onView(kept.id)}
        className={cn(
          "flex w-full cursor-default items-center gap-2.5 rounded-md border p-1.5 text-left focus-visible:focus-ring focus-visible:outline-none",
          viewing
            ? "border-accent-ink bg-accent-soft"
            : "border-line bg-panel hover:bg-hover",
        )}
      >
        <Thumb
          picture={versionPicture(image, kept, true)}
          shape={kept}
          className="size-12"
        />
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <span className="truncate mono-value">{image.name}</span>
          <span className="shrink-0 mono-annotation text-ink-muted">
            {kept.id}
          </span>
          <span className="shrink-0 mono-annotation text-ink-muted">
            {dimensions(kept.width, kept.height)}
          </span>
        </span>
        {elsewhere && <Icon name="link-out" className="text-ink-muted" />}
      </button>
    </li>
  );
}

/** One part of a run as the thread shows it. */
function RunBlock({
  image,
  run,
  block,
  opened,
  viewing,
  onView,
  renderCall,
  images,
  onOpenVersion,
}: {
  image: ImageSummary;
  run: Run;
  block: Block;
  opened: Record<string, boolean>;
  viewing: string | null;
  onView: (version: string) => void;
  renderCall?: (call: ImageCall) => ReactNode;
  images: ImageSummary[];
  onOpenVersion?: (name: string, version: string) => void;
}) {
  switch (block.kind) {
    case "message":
      return <Message block={block} />;
    case "said":
      return (
        <li className="shrink-0">
          <Markdown>{block.text}</Markdown>
        </li>
      );
    case "steps": {
      const key = `${image.name}:${block.key}`;
      const open = opened[key] ?? block.latest;
      return (
        <StepBlock
          calls={block.calls}
          started={block.started}
          finished={block.finished}
          state={block.state}
          open={open}
          onToggle={() => toggleOpened(key, !open)}
        />
      );
    }
    case "ended":
      return (
        <RunResult
          status={block.status}
          started={run.started}
          ended={block.ended}
          error={block.error}
          usage={block.usage}
        />
      );
    case "result": {
      const other = block.name;
      if (other === null) {
        return (
          <Result
            image={image}
            version={block.version}
            viewing={viewing === block.version}
            elsewhere={false}
            onView={onView}
          />
        );
      }
      const owner = images.find((each) => each.name === other);
      return owner ? (
        <Result
          image={owner}
          version={block.version}
          viewing={false}
          elsewhere
          onView={(version) => onOpenVersion?.(other, version)}
        />
      ) : null;
    }
    case "call":
      return <li className="shrink-0">{renderCall?.(block.call)}</li>;
    case "note":
      return (
        <li className="shrink-0 text-right text-caption text-ink-muted">
          {block.text}
        </li>
      );
  }
}

/** Where an image call this image's agent did not make starts: its number, when, and who wrote it. */
function CallDivider({ run, images }: { run: Run; images: ImageSummary[] }) {
  const call = run.blocks.find((block) => block.kind === "call")?.call;
  const keeper =
    call?.parentImage &&
    images.find((each) => each.id === call.parentImage)?.name;
  return (
    <li className="shrink-0">
      <Dimension tone="control">
        <span className="flex gap-2">
          <span>Run {run.number}</span>
          <span>{timeOfDay(run.started)}</span>
          {call && (
            <span>
              {keeper
                ? `The agent of ${keeper} wrote the call`
                : call.agent
                  ? "An agent wrote the call"
                  : `${call.sender} wrote the call`}
            </span>
          )}
        </span>
      </Dimension>
    </li>
  );
}

/**
 * An image's activity, run by run: what was asked of it and by whom, what its agent said and did, the image calls
 * that were made, how each run ended, and what it made.
 */
export function Thread({
  image,
  runs,
  label,
  viewing,
  onView,
  renderCall,
  images = [],
  onOpenVersion,
}: {
  image: ImageSummary | null;
  runs: Run[];
  /** What a model is called, by its id. */
  label: (model: string) => string;
  /** The version that shows, by its id. */
  viewing: string | null;
  onView: (version: string) => void;
  /** An image call as a card; a thread of runs that make none leaves it out. */
  renderCall?: (call: ImageCall) => ReactNode;
  /** Every image, for the other images a call in the thread was for or was made from. */
  images?: ImageSummary[];
  /** Bring up a version of another image, in that image's tab. */
  onOpenVersion?: (name: string, version: string) => void;
}) {
  const opened = useOpened();
  const list = useRef<HTMLOListElement>(null);
  const pinned = useRef(true);
  // When the person last scrolled, clicked, or pressed a key in the thread.
  const touched = useRef(0);
  const [behind, setBehind] = useState(false);
  const size = runs.reduce(
    (total, run) => total + run.blocks.length + run.calls.length,
    0,
  );

  useEffect(() => {
    if (pinned.current && list.current) {
      list.current.scrollTop = list.current.scrollHeight;
    }
  }, [size, image?.name]);

  // The thread also grows without a new entry, as when a version's card arrives after its run's, and gets shorter
  // when what is under it gets taller, as when a run starts. Neither may leave the latest entry out of view.
  useEffect(() => {
    const element = list.current;
    if (!element) {
      return;
    }
    const follow = () => {
      if (pinned.current) {
        element.scrollTop = element.scrollHeight;
      }
    };
    const resized = new ResizeObserver(follow);
    resized.observe(element);
    const grown = new MutationObserver(follow);
    grown.observe(element, { childList: true, subtree: true });
    return () => {
      resized.disconnect();
      grown.disconnect();
    };
  }, []);

  const touch = () => {
    touched.current = Date.now();
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <ol
        ref={list}
        onWheel={touch}
        onPointerDown={touch}
        onTouchMove={touch}
        onKeyDown={touch}
        onScroll={(event) => {
          const element = event.currentTarget;
          const at =
            element.scrollHeight - element.scrollTop - element.clientHeight <
            PINNED_PX;
          // Only the person scrolling away lets go of the bottom. The thread growing under a scroll made here would
          // otherwise read as having left it.
          if (at || Date.now() - touched.current < TOUCHED_MS) {
            pinned.current = at;
            setBehind(!at);
          }
        }}
        className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3"
      >
        {image &&
          runs.map((run) => (
            <Fragment key={run.id}>
              {run.kind === "call" ? (
                <CallDivider run={run} images={images} />
              ) : (
                <RunDivider run={run} label={label} />
              )}
              {run.blocks.map((block) => (
                <RunBlock
                  key={block.key}
                  image={image}
                  run={run}
                  block={block}
                  opened={opened}
                  viewing={viewing}
                  onView={onView}
                  renderCall={renderCall}
                  images={images}
                  onOpenVersion={onOpenVersion}
                />
              ))}
            </Fragment>
          ))}
      </ol>
      {behind && (
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            list.current?.scrollTo({
              top: list.current.scrollHeight,
              behavior: "smooth",
            })
          }
          className="absolute bottom-2.5 left-1/2 -translate-x-1/2 shadow-popover"
        >
          <Icon name="arrow-down" />
          Jump to latest
        </Button>
      )}
    </div>
  );
}
