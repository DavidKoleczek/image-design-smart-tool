import type { ImageSummary } from "@/lib/api";
import type { CanvasMode } from "@/lib/canvas";
import { useDraft } from "@/lib/drafts";
import { useMethods } from "@/lib/methods";
import {
  guideBlock,
  isDrawing,
  kindOf,
  makesNew,
  pickedModel,
  designModel,
} from "@/lib/request";
import { useSheet } from "@/lib/sheets";
import { useAppState } from "@/lib/state";
import { keyOf, type Tab } from "@/lib/tabs";
import type { Shown } from "@/lib/viewed";

export type Guidance = {
  /** Why marks, and why a mask, cannot guide the request now; null for one that can. */
  blocks: Record<CanvasMode, string | null>;
  /** What on the canvas guides the request; null when the image takes neither. */
  mode: CanvasMode | null;
  /** Whether marks can be drawn while a run works, for the next message to the agent working on the image. */
  steering: boolean;
};

/** How the canvas of a tab guides its request, as it shows `shown` of `image`; with no tab, as a new image's. */
export function useGuidance(
  tab: Tab | null,
  image: ImageSummary | null,
  shown: Shown | null,
): Guidance {
  const { state } = useAppState();
  const { methods } = useMethods();
  const draft = useDraft(tab ? keyOf(tab) : "");
  // The image call written by hand goes to the model picked in its editor, and the agent's to the one picked for it.
  const sheet = useSheet(tab ? keyOf(tab) : "");
  const method = tab?.method ?? state.method;
  const picked = tab?.mode ?? "markup";
  const model =
    methods && method === "model"
      ? sheet
        ? pickedModel(state.request.model, methods)
        : designModel(state.design.image_model, methods, image?.name ?? null)
      : null;
  const designing =
    method === "model" && !sheet && image?.design?.status === "running";
  // A request that makes a new image from the one in view takes neither marks nor a mask.
  const fresh =
    image !== null &&
    methods !== null &&
    makesNew(
      image,
      method,
      model,
      methods,
      kindOf(image, draft.kind, state.request, model),
    );
  const blocks: Record<CanvasMode, string | null> = {
    markup: guideBlock("markup", image, shown, model, fresh),
    // A message to the agent at work goes with marks only.
    mask: designing
      ? "The agent at work takes marks, not a mask"
      : guideBlock("mask", image, shown, model, fresh),
  };
  return {
    blocks,
    // A mode the image or the model does not take gives way to marks, which every model takes.
    mode:
      blocks[picked] === null
        ? picked
        : blocks.markup === null
          ? "markup"
          : null,
    // Marks drawn while an agent works on the image go to it with the next message.
    steering:
      designing ||
      (method === "svg" && image !== null && isDrawing(image.name)),
  };
}
