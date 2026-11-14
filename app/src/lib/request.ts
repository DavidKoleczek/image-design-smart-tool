import type {
  AppImageRequest,
  ImageListing,
  ImageMethods,
  ImageRequest,
  ImageSummary,
  SentMark,
  SentReference,
} from "@/lib/api";
import type { CanvasMode } from "@/lib/canvas";
import type { Reference } from "@/lib/references";
import type { Shown } from "@/lib/viewed";

/** What the model picker calls ChatGPT, which chooses the image model itself. */
export const CHATGPT = "chatgpt";
export const CHATGPT_LABEL = "Codex image generation";

/** `AppImageRequest()` in schemas.py, for when the state cannot be read. */
export const DEFAULT_REQUEST: AppImageRequest = {
  model: null,
  size: null,
  quality: "auto",
  format: ".png",
  background: "auto",
  count: 1,
  complexity: null,
  compression: 100,
  codex_model: null,
  reasoning_effort: null,
};

/** The sizes offered besides the service's own choice. */
export const SIZES: { label: string; size: [number, number] }[] = [
  { label: "Square", size: [1024, 1024] },
  { label: "Landscape", size: [1536, 1024] },
  { label: "Portrait", size: [1024, 1536] },
];

// In-progress images are asked for whenever the API sends them, so the image forms in the viewport.
const PREVIEWS = 2;
const NEW_NAME = "new-image";
const ANIMATION = ".gif";
const DRAWING = ".svg";
// The formats with no transparency, and those that take a compression level.
const OPAQUE = [".jpg"];
const COMPRESSED = [".jpg", ".webp"];

/** Why the canvas cannot guide a request to `model` one way, with marks or with a mask; null when it can. */
export function guideBlock(
  kind: CanvasMode,
  image: ImageSummary | null,
  shown: Shown | null,
  model: string | null,
): string | null {
  if (!image || !shown || shown.width === null) {
    return "Needs a source image";
  }
  if (kind === "mask") {
    if (extensionOf(image.name) === DRAWING) {
      return "A drawing does not take a mask";
    }
    if (model === CHATGPT) {
      return `${CHATGPT_LABEL} does not take a mask`;
    }
    if (shown.frames > 1) {
      return "An animation does not take a mask";
    }
  }
  return null;
}

/** A name's extension, lowercased, with its dot. */
export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

/** The formats a new image can be made in: what the OpenAI API makes, less the animation. */
export function stillFormats(methods: ImageMethods): string[] {
  return methods.openai.formats.filter((format) => format !== ANIMATION);
}

/**
 * The model the request goes to: the one picked last when it is still offered, else the default of the first method
 * that is set up.
 */
export function pickedModel(
  options: AppImageRequest,
  methods: ImageMethods,
): string {
  const { openai, chatgpt } = methods;
  if (
    options.model === CHATGPT ||
    openai.models.some((model) => model.id === options.model)
  ) {
    return options.model as string;
  }
  return openai.ready || !chatgpt.ready ? openai.default_model : CHATGPT;
}

/** What the picked options come to for this request: the options the model and the image's format do not take fall back. */
export type Resolved = {
  method: "openai" | "chatgpt";
  model: string;
  /** The extension the image's name ends in: the image's own on an edit. */
  format: string;
  size: [number, number] | null;
  background: string;
  count: number;
  /** Null where the format takes none. */
  compression: number | null;
  codexModel: string;
  reasoningEffort: string;
  /** Whether the format can have a transparent background. */
  transparency: boolean;
};

export function resolve(
  options: AppImageRequest,
  methods: ImageMethods,
  image: ImageSummary | null,
  /** The size asked of an edit of `image`; a new image takes the size picked last. */
  editSize: [number, number] | null,
): Resolved {
  const model = pickedModel(options, methods);
  const method = model === CHATGPT ? "chatgpt" : "openai";
  const offered = stillFormats(methods);
  const format = image
    ? extensionOf(image.name)
    : method === "chatgpt"
      ? methods.chatgpt.formats[0]
      : offered.includes(options.format)
        ? options.format
        : offered[0];
  const transparency = !OPAQUE.includes(format);
  const { chatgpt } = methods;
  const codexModel =
    chatgpt.models.find((each) => each.id === options.codex_model) ??
    chatgpt.models.find((each) => each.id === chatgpt.default_model);
  const efforts = codexModel?.reasoning_efforts ?? [];
  return {
    method,
    model,
    format,
    size:
      SIZES.find(({ size }) => same(size, image ? editSize : options.size))
        ?.size ?? null,
    background:
      options.background === "transparent" && !transparency
        ? "auto"
        : options.background,
    count:
      method === "openai" && format !== ANIMATION
        ? Math.min(options.count, methods.openai.max_count)
        : 1,
    compression: COMPRESSED.includes(format) ? options.compression : null,
    codexModel: codexModel?.id ?? chatgpt.default_model,
    reasoningEffort:
      options.reasoning_effort !== null &&
      efforts.includes(options.reasoning_effort)
        ? options.reasoning_effort
        : chatgpt.default_reasoning_effort,
    transparency,
  };
}

/** What the picked model is called. */
export function modelLabel(resolved: Resolved, methods: ImageMethods): string {
  return resolved.method === "chatgpt"
    ? CHATGPT_LABEL
    : (methods.openai.models.find((model) => model.id === resolved.model)
        ?.label ?? resolved.model);
}

/**
 * How many references the request can take: the images the model takes, less the image being edited and, where the
 * marks go on a copy of it, that copy.
 */
export function referenceRoom(
  resolved: Resolved,
  methods: ImageMethods,
  editing: boolean,
  marked: boolean,
): number {
  const taken =
    (editing ? 1 : 0) + (resolved.method === "chatgpt" && marked ? 1 : 0);
  return Math.max(0, methods[resolved.method].max_images - taken);
}

function same(a: [number, number] | null, b: [number, number] | null): boolean {
  return a !== null && b !== null && a[0] === b[0] && a[1] === b[1];
}

/** A name no image in the directory has, for a new image: `new-image`, then `new-image-2`, and so on. */
export function freeName(listing: ImageListing | null, format: string): string {
  const taken = new Set(
    (listing?.images ?? []).map((image) => image.name.toLowerCase()),
  );
  for (let count = 1; ; count += 1) {
    const name = count === 1 ? NEW_NAME : `${NEW_NAME}-${count}`;
    if (!taken.has(`${name}${format}`)) {
      return name;
    }
  }
}

/** A new image's name as typed, without an extension typed after it, since the format sets that. */
export function typedName(typed: string, formats: string[]): string {
  const name = typed.trim().replaceAll("\\", "/");
  const extension = extensionOf(name);
  return formats.includes(extension) || extension === DRAWING
    ? name.slice(0, -extension.length)
    : name;
}

/** What the request is for: an image in view and what of it shows, or a new image and the name it will have. */
export type Target =
  { image: ImageSummary; shown: Shown } | { image: null; name: string };

/** Why a request cannot be sent. A `quiet` one is plain from the form itself, so only the Generate button says it. */
export type Problem = {
  /** What it is in a few words, when `text` is the library's own account of what to set up. */
  title?: string;
  text: string;
  quiet: boolean;
};

/**
 * Why the request cannot be sent as it stands, for the person; null when it can. The library checks every request
 * again, so this only covers what the form can say sooner and in the app's terms.
 */
export function problemOf(
  target: Target,
  prompt: string,
  resolved: Resolved,
  methods: ImageMethods,
  listing: ImageListing | null,
  references: Reference[],
  /** How many references the request can take. */
  room: number,
): Problem | null {
  const method = methods[resolved.method];
  const loud = (text: string): Problem => ({ text, quiet: false });
  if (!method.ready) {
    return {
      title:
        resolved.method === "chatgpt"
          ? `${CHATGPT_LABEL} is not set up where the app runs.`
          : "The OpenAI API is not set up where the app runs.",
      text: method.problem ?? "",
      quiet: false,
    };
  }
  if (target.image) {
    if (resolved.format === DRAWING) {
      return loud("An image model can't change an SVG.");
    }
    if (!method.formats.includes(resolved.format)) {
      return loud(
        `${CHATGPT_LABEL} makes only PNG images. Pick an OpenAI API model to change this one.`,
      );
    }
  } else {
    if (target.name === "") {
      return { text: "Give the image a name.", quiet: true };
    }
    const wanted = `${target.name}${resolved.format}`.toLowerCase();
    if (listing?.images.some((image) => image.name.toLowerCase() === wanted)) {
      return loud("Another image already has that name.");
    }
  }
  const failed = references.find((reference) => reference.state === "failed");
  if (failed) {
    return loud(
      `${failed.name} did not reach the app. Remove it and add it again.`,
    );
  }
  if (references.length > room) {
    return loud(
      `${modelLabel(resolved, methods)} takes ${method.max_images} images in a request, counting the image being edited${resolved.method === "chatgpt" ? " and its marked copy" : ""}. Remove a reference.`,
    );
  }
  if (references.some((reference) => reference.state === "uploading")) {
    return { text: "A reference is still being added.", quiet: true };
  }
  return prompt.trim() === "" ? { text: "Write a prompt.", quiet: true } : null;
}

/** What guides a request besides its prompt, as the tools take it. */
export type SentGuide = {
  references: SentReference[];
  marks: SentMark[];
  /** The upload holding the mask; null for none. */
  mask: string | null;
};

/** The request as the library takes it. */
export function requestOf(
  target: Target,
  prompt: string,
  options: AppImageRequest,
  resolved: Resolved,
  methods: ImageMethods,
  guide: SentGuide,
): ImageRequest {
  const guides = {
    ...(guide.references.length > 0 ? { references: guide.references } : {}),
    ...(guide.marks.length > 0 ? { marks: guide.marks } : {}),
  };
  const name = target.image
    ? target.image.name
    : `${target.name}${resolved.format}`;
  // A version that is not what the image's file holds is edited by its id; the file itself, as it is.
  const version =
    target.image && !target.shown.file && target.shown.version
      ? { version: target.shown.version.id }
      : {};
  if (resolved.method === "chatgpt") {
    return {
      method: "chatgpt",
      arguments: {
        prompt,
        name,
        ...version,
        ...guides,
        transparent: resolved.background === "transparent",
        model: resolved.codexModel,
        reasoning_effort: resolved.reasoningEffort,
      },
    };
  }
  return {
    method: "openai",
    arguments: {
      prompt,
      name,
      ...version,
      ...guides,
      ...(guide.mask !== null ? { mask: guide.mask } : {}),
      model: resolved.model,
      ...(resolved.size ? { size: resolved.size } : {}),
      quality: options.quality,
      ...(options.complexity ? { complexity: options.complexity } : {}),
      background: resolved.background,
      ...(resolved.compression !== null
        ? { compression: resolved.compression }
        : {}),
      count: resolved.count,
      // The API sends none with several images, or for an animation.
      previews:
        resolved.count === 1 && resolved.format !== ANIMATION
          ? Math.min(PREVIEWS, methods.openai.max_previews)
          : 0,
    },
  };
}
