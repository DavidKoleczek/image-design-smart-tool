import type {
  AppImageRequest,
  AppMethod,
  ImageListing,
  ImageMethods,
  ImageRequest,
  ImageSummary,
  SentMark,
  SentReference,
} from "@/lib/api";
import type { CanvasMode } from "@/lib/canvas";
import { baseName, joined, typedProblem } from "@/lib/paths";
import { framePicture, type Picture } from "@/lib/pictures";
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
  kind: "image",
  frame_size: null,
  frames: 8,
  frame_ms: 200,
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

/** The sizes offered for an animation, whose frames are smaller than a still image. */
export const FRAME_SIZES: { label: string; size: [number, number] }[] = [
  { label: "Square", size: [512, 512] },
  { label: "Landscape", size: [768, 512] },
  { label: "Portrait", size: [512, 768] },
];

// In-progress images are asked for whenever the API sends them, so the image forms in the viewport.
const PREVIEWS = 2;
const NEW_NAME = "new-image";
/** The extension of an animation, which only the OpenAI API makes and changes. */
export const ANIMATION = ".gif";
/** The extension of a drawing, which only the SVG method makes and changes. */
export const DRAWING = ".svg";
// The formats with no transparency, and those that take a compression level.
const OPAQUE = [".jpg", ANIMATION];
const COMPRESSED = [".jpg", ".webp"];

export function isDrawing(name: string): boolean {
  return extensionOf(name) === DRAWING;
}

export function isAnimation(name: string): boolean {
  return extensionOf(name) === ANIMATION;
}

/** What a request makes: a still image, or an animation. */
export type Kind = AppImageRequest["kind"];

/**
 * What a request to `model` makes: what the person `picked` for the image in view, and until they pick, what that
 * image is. A new image is what was picked last. Only the OpenAI API makes an animation.
 */
export function kindOf(
  image: ImageSummary | null,
  picked: Kind | null,
  options: AppImageRequest,
  model: string | null,
): Kind {
  if (model === CHATGPT) {
    return "image";
  }
  if (image === null) {
    return options.kind;
  }
  return picked ?? (isAnimation(image.name) ? "animation" : "image");
}

/**
 * Whether a request on `image` by `method` makes a new image from it rather than changing it, since the method cannot
 * change a file of its type, or the request makes another type: an image model on a drawing, ChatGPT on an image that
 * is not a PNG, SVG on a raster, an animation of a still image, or a still image of one frame of an animation.
 */
export function makesNew(
  image: ImageSummary,
  method: AppMethod,
  model: string | null,
  methods: ImageMethods,
  kind: Kind,
): boolean {
  if (method === "svg") {
    return !isDrawing(image.name);
  }
  return (
    isDrawing(image.name) ||
    (model === CHATGPT &&
      !methods.chatgpt.formats.includes(extensionOf(image.name))) ||
    (kind === "animation") !== isAnimation(image.name)
  );
}

/**
 * Why the canvas cannot guide a request to `model` one way, with marks or with a mask; null when it can. `fresh` is
 * whether the request makes a new image from the one in view.
 */
export function guideBlock(
  kind: CanvasMode,
  image: ImageSummary | null,
  shown: Shown | null,
  model: string | null,
  fresh: boolean,
): string | null {
  if (!image || !shown || shown.width === null) {
    return "Needs a source image";
  }
  if (fresh) {
    return kind === "mask"
      ? "A new image takes no mask"
      : "A new image takes no marks";
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

const QUALITY_LABELS: Record<string, string> = { xhigh: "Extra high" };

/** What an image quality is called. */
export function qualityLabel(quality: string): string {
  return (
    QUALITY_LABELS[quality] ??
    quality.charAt(0).toUpperCase() + quality.slice(1)
  );
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
 * The image model a request goes to: the one picked last when it is still offered, else the default of the first
 * method that is set up.
 */
export function pickedModel(
  picked: string | null,
  methods: ImageMethods,
): string {
  const { openai, chatgpt } = methods;
  if (
    picked === CHATGPT ||
    openai.models.some((model) => model.id === picked)
  ) {
    return picked as string;
  }
  return openai.ready || !chatgpt.ready ? openai.default_model : CHATGPT;
}

/**
 * The image model the image's agent is given, as `design_image` picks it: the one picked last when it is still
 * offered, else the first of the person's order that is set up and makes the image named, any image for a new one.
 */
export function designModel(
  picked: string | null,
  methods: ImageMethods,
  name: string | null,
): string {
  const { openai, chatgpt, design } = methods;
  if (
    picked === CHATGPT ||
    openai.models.some((model) => model.id === picked)
  ) {
    return picked as string;
  }
  const extension = name === null ? null : extensionOf(name);
  const methodOf = (model: string) => (model === CHATGPT ? chatgpt : openai);
  const ready = design.image_models.filter((model) => methodOf(model).ready);
  const makes = ready.filter(
    (model) =>
      extension === null ||
      !design.formats.includes(extension) ||
      methodOf(model).formats.includes(extension),
  );
  return makes[0] ?? ready[0] ?? design.default_image_model;
}

/** What the picked options come to for this request: the options the model and the image's format do not take fall back. */
export type Resolved = {
  method: "openai" | "chatgpt";
  model: string;
  /** The extension the image's name ends in: the image's own on an edit. */
  format: string;
  kind: Kind;
  size: [number, number] | null;
  background: string;
  /**
   * For an animation, how many frames it has and how long each shows; null to keep those of the animation being
   * edited, and for a still image.
   */
  frames: number | null;
  frameMs: number | null;
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
  /** The image the request changes; null for a new image, also one made from the image in view. */
  image: ImageSummary | null,
  /** What a new image is: a still image, or an animation. An image being changed stays what it is. */
  kind: Kind,
  /** What was asked of an edit of `image`; a new image takes what was picked last. */
  edit: {
    size: [number, number] | null;
    frames: number | null;
    frameMs: number | null;
  },
): Resolved {
  const model = pickedModel(options.model, methods);
  const method = model === CHATGPT ? "chatgpt" : "openai";
  const offered = stillFormats(methods);
  const format = image
    ? extensionOf(image.name)
    : method === "chatgpt"
      ? methods.chatgpt.formats[0]
      : kind === "animation"
        ? ANIMATION
        : offered.includes(options.format)
          ? options.format
          : offered[0];
  const animated = format === ANIMATION;
  const transparency = !OPAQUE.includes(format);
  const [fewest, most] = methods.openai.frames;
  const [shortest, longest] = methods.openai.frame_ms;
  const within = (value: number, low: number, high: number) =>
    Math.min(high, Math.max(low, value));
  const { chatgpt } = methods;
  const codexModel =
    chatgpt.models.find((each) => each.id === options.codex_model) ??
    chatgpt.models.find((each) => each.id === chatgpt.default_model);
  const efforts = codexModel?.reasoning_efforts ?? [];
  return {
    method,
    model,
    format,
    kind: animated ? "animation" : "image",
    size:
      (animated ? FRAME_SIZES : SIZES).find(({ size }) =>
        same(
          size,
          image ? edit.size : animated ? options.frame_size : options.size,
        ),
      )?.size ?? null,
    background:
      options.background === "transparent" && !transparency
        ? "auto"
        : options.background,
    frames: !animated
      ? null
      : image
        ? edit.frames && within(edit.frames, fewest, most)
        : within(options.frames, fewest, most),
    frameMs: !animated
      ? null
      : image
        ? edit.frameMs && within(edit.frameMs, shortest, longest)
        : within(options.frame_ms, shortest, longest),
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
  return imageModelLabel(resolved.model, methods);
}

/** What an image model a request can go to is called: an OpenAI image model's id, or `chatgpt`. */
export function imageModelLabel(model: string, methods: ImageMethods): string {
  return model === CHATGPT
    ? CHATGPT_LABEL
    : (methods.openai.models.find((each) => each.id === model)?.label ?? model);
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

/**
 * A name no image in the directory has, without its extension: `wanted`, then `wanted-2`, and so on. By default
 * `new-image`, for a new image.
 */
export function freeName(
  listing: ImageListing | null,
  format: string,
  wanted: string = NEW_NAME,
): string {
  const taken = new Set(
    (listing?.images ?? []).map((image) => image.name.toLowerCase()),
  );
  for (let count = 1; ; count += 1) {
    const name = count === 1 ? wanted : `${wanted}-${count}`;
    if (!taken.has(`${name}${format}`.toLowerCase())) {
      return name;
    }
  }
}

/** A name for a new image in `folder` that no image there has, without the folder or the extension. */
export function freeNewName(
  listing: ImageListing | null,
  format: string,
  folder: string,
): string {
  return baseName(freeName(listing, format, joined(folder, NEW_NAME)));
}

/** The folder a new image goes in: the one picked, while the directory has it, and otherwise the top. */
export function folderIn(listing: ImageListing | null, picked: string): string {
  return listing?.folders.includes(picked) ? picked : "";
}

/** An image's name without its extension, in its folder. */
export function stem(name: string): string {
  const extension = extensionOf(name);
  return extension ? name.slice(0, -extension.length) : name;
}

/** A new image's name in `folder` as typed, before the extension its format sets; "" while none is typed. */
export function typedName(typed: string, folder: string): string {
  const name = typed.trim().replaceAll("\\", "/");
  return name && joined(folder, name);
}

/**
 * An image in view, and what of it shows. Of an animation a request sends one `frame`, which is null for anything
 * else.
 */
export type Source = {
  image: ImageSummary;
  shown: Shown;
  frame: number | null;
};

/**
 * What the request is for: an image in view, or a new image and the name it will have without its extension. A new
 * image made `from` the image in view has it as its first reference.
 */
export type Target =
  | (Source & { from?: undefined })
  | { image: null; name: string; from: Source | null };

/** The file of what shows of an image: the version in view, or the image's file. */
export function sourcePath(source: Source): string {
  return source.shown.version && !source.shown.file
    ? source.shown.version.file
    : source.image.path;
}

/** What a request sends of an image in view, to show: the frame it sends of an animation, or what shows of it. */
export function sourcePicture(source: Source, small = false): Picture | null {
  const picture = source.shown.picture;
  if (picture === null) {
    return null;
  }
  return source.frame === null
    ? { ...picture, small }
    : framePicture(picture, source.frame, small);
}

/** The name, without its extension, of a new image made from an image in view: a still of one frame says which. */
export function nameFrom(source: Source, kind: Kind | null): string {
  const name = stem(source.image.name);
  return source.frame !== null && kind === "image"
    ? `${name}-frame-${source.frame + 1}`
    : name;
}

/** The image a new one is made from, as the first of the references it is sent with. */
export function sourceReference(source: Source): SentReference {
  return {
    path: sourcePath(source),
    ...(source.frame !== null ? { frame: source.frame } : {}),
  };
}

/** Whether the request sends an image in view, as the image it edits or as the one a new image is made from. */
export function sendsSource(target: Target): boolean {
  return target.image !== null || target.from !== null;
}

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
  if (!target.image) {
    if (target.name === "") {
      return { text: "Give the image a name.", quiet: true };
    }
    const typed =
      target.from === null && typedProblem(target.name, resolved.format);
    if (typed) {
      return loud(typed);
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
  const references = target.from
    ? [sourceReference(target.from), ...guide.references]
    : guide.references;
  const guides = {
    ...(references.length > 0 ? { references } : {}),
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
      ...(target.image && target.frame !== null ? { frame: target.frame } : {}),
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
      ...(resolved.frames !== null ? { frames: resolved.frames } : {}),
      ...(resolved.frameMs !== null ? { frame_ms: resolved.frameMs } : {}),
      // The API sends none for an animation.
      previews:
        resolved.kind === "image"
          ? Math.min(PREVIEWS, methods.openai.max_previews)
          : 0,
    },
  };
}
