import { Icon, type IconName } from "@/components/ui/icon";
import { Tooltip } from "@/components/ui/tooltip";
import { setTool, useCanvas, type CanvasMode, type Tool } from "@/lib/canvas";
import { useShortcuts } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

type Entry = { tool: Tool; label: string; key: string; icon: IconName };

const SELECT: Entry = {
  tool: "select",
  label: "Select",
  key: "V",
  icon: "select",
};
const PAN: Entry = { tool: "pan", label: "Pan", key: "H", icon: "move" };
const MARKUP: Entry[] = [
  { tool: "circle", label: "Circle", key: "O", icon: "circle" },
  { tool: "box", label: "Box", key: "R", icon: "box" },
  { tool: "arrow", label: "Arrow", key: "A", icon: "arrow" },
  { tool: "sketch", label: "Sketch", key: "P", icon: "draw" },
];
const MASK: Entry[] = [
  { tool: "brush", label: "Paint mask", key: "B", icon: "area" },
  { tool: "eraser", label: "Erase mask", key: "E", icon: "eraser" },
];

/** The tools of the mode the canvas is in, down its left edge. `blocked` says why none can be used now. */
export function ToolStrip({
  mode,
  blocked,
}: {
  mode: CanvasMode;
  blocked: string | null;
}) {
  const { tool } = useCanvas();
  const tools = [
    ...(mode === "markup" ? [SELECT] : []),
    PAN,
    ...(mode === "markup" ? MARKUP : MASK),
  ];
  useShortcuts(
    blocked
      ? {}
      : Object.fromEntries(
          tools.map((entry) => [
            entry.key.toLowerCase(),
            () => setTool(entry.tool),
          ]),
        ),
  );
  return (
    <div
      role="toolbar"
      aria-label="Tools"
      aria-orientation="vertical"
      className="flex w-11 shrink-0 flex-col items-center gap-1 border-r border-line bg-panel py-2"
    >
      {tools.map((entry) => (
        <div key={entry.tool} className="contents">
          <Tooltip
            content={blocked ? `${entry.label}: ${blocked}` : entry.label}
            keys={blocked ? undefined : entry.key}
            side="right"
          >
            <button
              type="button"
              aria-label={entry.label}
              aria-pressed={!blocked && tool === entry.tool}
              aria-disabled={blocked ? true : undefined}
              onClick={() => !blocked && setTool(entry.tool)}
              className={cn(
                "grid size-7 cursor-default place-items-center rounded-md border border-transparent focus-visible:focus-ring focus-visible:outline-none",
                blocked
                  ? "text-ink-faint"
                  : tool === entry.tool
                    ? "border-line-control bg-field text-accent-ink"
                    : "text-ink hover:bg-hover",
              )}
            >
              <Icon name={entry.icon} size={20} />
            </button>
          </Tooltip>
          {entry === PAN && (
            <span aria-hidden className="mt-1 h-px w-5 bg-line" />
          )}
        </div>
      ))}
    </div>
  );
}
