import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Tooltip } from "@/components/ui/tooltip";
import {
  pausePlayback,
  playFrame,
  setLoop,
  showFrame,
  togglePlayback,
  useLoop,
  type Playback,
} from "@/lib/frames";
import {
  framePicture,
  readAhead,
  usePicture,
  type Picture,
} from "@/lib/pictures";
import { useShortcuts } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

// The widest a frame is drawn before the timeline is zoomed in, and the widest it gets when it is.
const FRAME_WIDTH = 72;
const FRAME_WIDEST = 160;
const ZOOM_STEP = 1.5;
// The times between ruler ticks, in milliseconds, of which the first that leaves this much room on screen is used.
const TICK_STEPS = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000];
const TICK_ROOM = 48;
// What the frames are inset from each side of the pane.
const INSET = 12;
// From this width a frame has room for its number.
const NUMBERED_FROM = 30;

function seconds(ms: number): string {
  return String(Number((ms / 1000).toFixed(2)));
}

function Frame({
  of,
  index,
  left,
  width,
  current,
}: {
  of: Picture;
  index: number;
  left: number;
  width: number;
  current: boolean;
}) {
  const { url } = usePicture(framePicture(of, index, true));
  return (
    // Out of the tab order, since an animation can have hundreds: the keys and the buttons above step through them.
    <button
      type="button"
      tabIndex={-1}
      aria-label={`Frame ${index + 1}`}
      aria-current={current || undefined}
      onClick={() => showFrame(of.name, index)}
      style={{ left, width }}
      className={cn(
        "absolute inset-y-0 cursor-pointer overflow-hidden border-r border-panel bg-field",
        current && "z-1 outline-2 -outline-offset-2 outline-accent-ink",
      )}
    >
      {url && (
        <img
          src={url}
          alt=""
          draggable={false}
          className="pointer-events-none block size-full object-cover"
        />
      )}
      {width >= NUMBERED_FROM && (
        <span
          className={cn(
            "absolute bottom-0.75 left-0.75 px-1 mono-annotation",
            current ? "bg-accent text-on-accent" : "bg-panel/90 text-ink",
          )}
        >
          {index + 1}
        </span>
      )}
    </button>
  );
}

/**
 * An animation over time: the controls that play it and step through it, then a ruler in seconds, each frame as wide
 * as it lasts, and a playhead. A handful of frames reads as a strip of them; many thin to slivers until the timeline
 * is zoomed in. It also plays the animation, moving on to each frame once the one before has had its time.
 */
export function Timeline({
  of,
  count,
  playback,
  durations,
  marked,
  open,
}: {
  /** The animation as a whole, whose frames these are. */
  of: Picture;
  count: number;
  playback: Playback;
  /** How long each frame shows, in milliseconds; null until it is read. */
  durations: number[] | null;
  /** The frame the marks for the next request are on; null when it has none. */
  marked: number | null;
  /** Whether the frames show under the controls; folded, the controls alone leave the image more room. */
  open: boolean;
}) {
  const [room, setRoom] = useState(0);
  const [zoomed, setZoomed] = useState(1);
  const track = useRef<HTMLDivElement>(null);
  const scrollerElement = useRef<HTMLDivElement | null>(null);
  const loop = useLoop();
  const { name, version, key } = of;
  const whole = useMemo<Picture>(
    () => ({ name, version, small: false, preview: null, key }),
    [name, version, key],
  );
  const frames = durations?.length ?? count;
  const at = Math.min(playback.frame, frames - 1);
  const { playing } = playback;

  const scroller = useCallback((element: HTMLDivElement | null) => {
    scrollerElement.current = element;
    if (!element) {
      return;
    }
    const observer = new ResizeObserver(() => setRoom(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!playing || durations === null) {
      return;
    }
    const next = at + 1 < durations.length ? at + 1 : loop ? 0 : null;
    if (next === null) {
      const timer = window.setTimeout(() => pausePlayback(name), durations[at]);
      return () => window.clearTimeout(timer);
    }
    let current = true;
    // Read while this frame shows, so the next is there when its time comes. One slow to arrive holds this one.
    const read = readAhead(framePicture(whole, next));
    const timer = window.setTimeout(() => {
      read.then(
        () => current && playFrame(name, next),
        () => current && pausePlayback(name),
      );
    }, durations[at]);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [name, whole, playing, at, loop, durations]);

  const step = (by: number) => showFrame(name, (at + by + frames) % frames);
  const toggle = () => togglePlayback(name, frames - 1);

  useShortcuts({
    ",": () => step(-1),
    ".": () => step(1),
    " ": toggle,
  });

  const starts: number[] = [];
  let elapsed = 0;
  for (const each of durations ?? []) {
    starts.push(elapsed);
    elapsed += each;
  }
  const total = elapsed || 1;
  const average = total / frames;
  const base = Math.min(
    Math.max(0, room - 2 * INSET) / total,
    FRAME_WIDTH / average,
  );
  const most = Math.max(1, FRAME_WIDEST / (base * average || 1));
  const zoom = Math.min(most, Math.max(1, zoomed));
  // Pixels to a millisecond.
  const scale = base * zoom;
  const start = starts[at] ?? 0;
  const length = durations?.[at] ?? 0;

  // The frame that shows stays inside the part of the timeline that is scrolled into view.
  useEffect(() => {
    const element = scrollerElement.current;
    if (!element) {
      return;
    }
    const from = start * scale;
    const to = from + length * scale + 2 * INSET;
    if (from < element.scrollLeft) {
      element.scrollLeft = from;
    } else if (to > element.scrollLeft + element.clientWidth) {
      element.scrollLeft = to - element.clientWidth;
    }
  }, [start, length, scale]);

  const frameUnder = (clientX: number): number => {
    const left = track.current?.getBoundingClientRect().left ?? 0;
    const time = (clientX - left) / scale;
    let index = 0;
    while (index + 1 < starts.length && starts[index + 1] <= time) {
      index += 1;
    }
    return index;
  };

  // The drag is followed on the window, so scrubbing keeps going when the pointer leaves the timeline.
  const scrub = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || durations === null) {
      return;
    }
    event.preventDefault();
    showFrame(name, frameUnder(event.clientX));
    const move = (moved: globalThis.PointerEvent) =>
      showFrame(name, frameUnder(moved.clientX));
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  };

  const tick =
    TICK_STEPS.find((candidate) => candidate * scale >= TICK_ROOM) ?? 60000;
  const ticks: number[] = [];
  for (let time = 0; durations !== null && time <= total; time += tick) {
    ticks.push(time);
  }

  return (
    <section
      aria-label="Timeline"
      className="shrink-0 border-t border-line bg-panel"
    >
      <header className="flex h-9 items-center gap-1 pr-2 pl-3 whitespace-nowrap">
        <h2 className="mr-2 text-label">Timeline</h2>
        <Tooltip content="Previous frame" keys="," side="top">
          <Button
            size="sm"
            icon
            aria-label="Previous frame"
            onClick={() => step(-1)}
          >
            <Icon name="step-back" />
          </Button>
        </Tooltip>
        <Tooltip content={playing ? "Pause" : "Play"} keys="Space" side="top">
          <Button
            size="sm"
            icon
            aria-label={playing ? "Pause" : "Play"}
            onClick={toggle}
          >
            <Icon name={playing ? "pause" : "play"} />
          </Button>
        </Tooltip>
        <Tooltip content="Next frame" keys="." side="top">
          <Button
            size="sm"
            icon
            aria-label="Next frame"
            onClick={() => step(1)}
          >
            <Icon name="step-forward" />
          </Button>
        </Tooltip>
        <Tooltip content="Loop" side="top">
          <Button
            size="sm"
            icon
            aria-label="Loop"
            aria-pressed={loop}
            onClick={() => setLoop(!loop)}
          >
            <Icon name="loop" />
          </Button>
        </Tooltip>
        <span className="ml-2 mono-value">
          frame {at + 1} of {frames}
        </span>
        {durations && (
          <span className="ml-2 truncate mono-annotation text-ink-muted">
            {(start / 1000).toFixed(2)} of {(total / 1000).toFixed(2)} s
          </span>
        )}
        <span className="flex-1" />
        {open && (
          <>
            <Tooltip content="Zoom the timeline out" side="top">
              <Button
                size="sm"
                icon
                aria-label="Zoom the timeline out"
                disabled={zoom <= 1}
                onClick={() => setZoomed(Math.max(1, zoom / ZOOM_STEP))}
              >
                <Icon name="minus" />
              </Button>
            </Tooltip>
            <Tooltip content="Zoom the timeline in" side="top">
              <Button
                size="sm"
                icon
                aria-label="Zoom the timeline in"
                disabled={zoom >= most}
                onClick={() => setZoomed(Math.min(most, zoom * ZOOM_STEP))}
              >
                <Icon name="add" />
              </Button>
            </Tooltip>
          </>
        )}
      </header>
      {open && (
        <div ref={scroller} className="overflow-x-auto px-3 pb-2">
          <div
            ref={track}
            onPointerDown={scrub}
            style={{ width: total * scale }}
            className="relative h-17.5 min-w-full touch-none select-none"
          >
            <div
              aria-hidden
              className="absolute inset-x-0 top-0 h-4 border-b border-line mono-annotation text-ink-muted"
            >
              {ticks.map((time) => (
                <span
                  key={time}
                  style={{ left: time * scale }}
                  className="absolute inset-y-0 border-l border-line-control"
                >
                  <span className="absolute top-0 left-1 leading-3.5">
                    {seconds(time)}s
                  </span>
                </span>
              ))}
            </div>
            {marked !== null && durations && marked < frames && (
              <Tooltip content={`Frame ${marked + 1} has the marks`} side="top">
                <span
                  style={{
                    left: starts[marked] * scale,
                    width: durations[marked] * scale,
                  }}
                  className="absolute top-4.5 h-1 bg-accent-ink"
                />
              </Tooltip>
            )}
            <div className="absolute inset-x-0 top-6 h-11.5">
              {durations?.map((duration, index) => (
                <Frame
                  key={index}
                  of={whole}
                  index={index}
                  left={starts[index] * scale}
                  width={duration * scale}
                  current={index === at}
                />
              ))}
            </div>
            {durations && (
              <span
                aria-hidden
                style={{ left: start * scale }}
                className="pointer-events-none absolute inset-y-0 z-2 w-px bg-accent-ink before:absolute before:top-0 before:-left-1 before:size-2.25 before:bg-accent-ink"
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}
