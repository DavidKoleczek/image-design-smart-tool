import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Without these, `text-body` reads as a text color and `cn` drops it beside `text-ink`.
const twMerge = extendTailwindMerge({
  extend: {
    theme: { text: ["display", "title", "body", "label", "caption"] },
    classGroups: { "font-size": ["mono-value", "mono-annotation"] },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
