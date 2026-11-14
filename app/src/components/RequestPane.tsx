import { Notice } from "@/components/ui/notice";
import { Segmented } from "@/components/ui/segmented";
import type { AppMethod } from "@/lib/api";
import { updateAppState, useAppState } from "@/lib/state";

/** The pane on the right: the way of making an image, and under it what that way asks for. */
export function RequestPane() {
  const { state, error } = useAppState();
  return (
    <aside
      aria-label="Request"
      className="flex h-full min-w-0 flex-col bg-panel"
    >
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-line pr-2 pl-3">
        <span className="text-label text-ink-muted">Method</span>
        <Segmented<AppMethod>
          label="Method"
          value={state.method}
          onChange={(method) =>
            updateAppState((current) => ({ ...current, method }))
          }
          options={[
            { value: "model", label: "Image model" },
            { value: "svg", label: "SVG" },
          ]}
        />
      </header>
      {error && <Notice className="m-2">{error}</Notice>}
      <div className="min-h-0 flex-1 overflow-y-auto" />
    </aside>
  );
}
