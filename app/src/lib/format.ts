import type { ImageMethod, ImageUsage } from "@/lib/api";

const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const count = new Intl.NumberFormat();

const METHODS: Record<ImageMethod, string> = {
  openai: "OpenAI API",
  chatgpt: "ChatGPT",
  svg: "SVG",
  imported: "imported",
};

/** A width and height in pixels, with the multiplication sign between them. */
export function dimensions(width: number, height: number): string {
  return `${width} \u00d7 ${height}`;
}

/** What made a version, as the app names the method. */
export function methodLabel(method: ImageMethod): string {
  return METHODS[method];
}

/** What a run used: dollars when it reported them, its tokens otherwise, and nothing when it reported neither. */
export function usageLabel(usage: ImageUsage | null): string | null {
  if (usage === null) {
    return null;
  }
  if (usage.cost !== null) {
    return usage.cost > 0 && usage.cost < 0.01
      ? "under $0.01"
      : dollars.format(usage.cost);
  }
  const tokens =
    usage.input_text_tokens + usage.input_image_tokens + usage.output_tokens;
  return tokens > 0 ? `${count.format(tokens)} tokens` : null;
}
