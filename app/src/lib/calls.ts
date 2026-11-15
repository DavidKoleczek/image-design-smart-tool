import type { IconName } from "@/components/ui/icon";
import type { CallRole, ImageCall } from "@/lib/thread";

export const ROLE_LABELS: Record<CallRole, string> = {
  source: "source",
  "marked-copy": "marked copy",
  reference: "reference",
  marks: "marks layer",
  mask: "mask",
};
export const ROLE_ICONS: Record<CallRole, IconName> = {
  source: "image",
  "marked-copy": "mark",
  reference: "image",
  marks: "circle",
  mask: "area",
};
// What goes beside the images rather than among them, so it has no number of its own.
export const BESIDE: CallRole[] = ["marks", "mask"];

/** The number each image of a call has in its prompt, counting those sent among the images from 1. */
export function numbered(
  images: ImageCall["images"],
): { path: string; role: CallRole; number: number | null }[] {
  let count = 0;
  return images.map((image) => {
    if (BESIDE.includes(image.role)) {
      return { ...image, number: null };
    }
    count += 1;
    return { ...image, number: count };
  });
}
