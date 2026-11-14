import type { CallToolResult } from "@modelcontextprotocol/client";

import { AppError } from "@/lib/errors";
import { app } from "@/lib/host";

const LIST_TOOL = "list_images";
const VIEW_TOOL = "view_image";
const MOVE_TOOL = "move_image";
const DELETE_TOOL = "delete_image";
const RESTORE_TOOL = "restore_image_version";
const ACTIVITY_TOOL = "read_image_activity";
const METHODS_TOOL = "list_image_methods";
const GENERATE_TOOLS = {
  openai: "generate_openai_image",
  chatgpt: "generate_chatgpt_image",
};
const PREVIEW_TOOLS = {
  openai: "preview_openai_image_request",
  chatgpt: "preview_chatgpt_image_request",
};
const CANCEL_TOOL = "cancel_image";
const UPLOAD_TOOL = "upload_file";
const LIBRARY_TOOL = "read_reference_library";
const FOLDER_TOOL = "list_reference_folder";
const CHOOSE_FILES_TOOL = "choose_reference_files";
const CHOOSE_FOLDER_TOOL = "choose_reference_folder";
const KEEP_TOOL = "keep_reference";
const READ_KEY_TOOL = "read_openai_key";
const ENTER_KEY_TOOL = "enter_openai_key";
const CLEAR_KEY_TOOL = "clear_openai_key";
const READ_SETTINGS_TOOL = "read_app_settings";
const SAVE_SETTINGS_TOOL = "save_app_settings";
const READ_STATE_TOOL = "read_app_state";
const SAVE_STATE_TOOL = "save_app_state";
const IMAGE_FILE_PREFIX = "image-design://images/";
const IMAGE_VERSION_PREFIX = "image-design://versions/";
const IMAGE_THUMBNAIL_PREFIX = "image-design://thumbnails/";
const RUN_PREVIEW_PREFIX = "image-design://previews/";
const REFERENCE_PREFIX = "image-design://references/";
// In a thumbnail URI, names the image file where a version id would be.
const FILE = "file";

/** `ImageRunStatus` in schemas.py. */
export type ImageRunStatus =
  "running" | "done" | "failed" | "cancelled" | "timed-out";

/** `ImageMethod` in schemas.py: what made a version. */
export type ImageMethod = "openai" | "chatgpt" | "svg" | "imported";

/** `ImageUsage` in schemas.py. */
export type ImageUsage = {
  input_text_tokens: number;
  input_image_tokens: number;
  output_tokens: number;
  /** US dollars; null when the run reported none. */
  cost: number | null;
};

/** The fields of `ImageVersion` in schemas.py that the view reads. */
export type ImageVersion = {
  /** v1, v2, and so on. */
  id: string;
  width: number;
  height: number;
  /** More than 1 for an animation. */
  frames: number;
  sha256: string;
  method: ImageMethod;
  run_id: string | null;
  /** ISO 8601. */
  created: string;
};

/** The fields of `ImageRunRecord` in schemas.py that the view reads. */
export type ImageRun = {
  id: string;
  method: ImageMethod;
  prompt: string;
  /** The settings it was sent with, by the names the method records them under. */
  request: Record<string, unknown>;
  /** The versions it has made so far. */
  versions: string[];
  /** ISO 8601. */
  started: string;
  /** Why it failed or timed out, as the library words it. */
  error: string | null;
};

/** The fields of `ImageSummary` in schemas.py that the view reads. */
export type ImageSummary = {
  /** The image's path in the directory, with forward slashes. */
  name: string;
  /** The image's file, on the machine the app runs on. */
  path: string;
  /** Of the image's file; null when it has none, or one that cannot be read. */
  width: number | null;
  height: number | null;
  frames: number | null;
  /** When the file was last written, ISO 8601. */
  modified: string | null;
  /** Of the file's content; null when it has no file. */
  sha256: string | null;
  /** The version in the image's file; null when the file was changed by hand since, or has no versions. */
  current: string | null;
  versions: ImageVersion[];
  status: ImageRunStatus | null;
  last_run: ImageRun | null;
};

/** `ImageEvent` in schemas.py. */
export type ImageEvent = {
  /** ISO 8601. */
  time: string;
  run_id: string;
  kind:
    | "started"
    | "preview"
    | "agent"
    | "steered"
    | "version"
    | "finished"
    | "failed";
  text: string;
  data: Record<string, unknown>;
};

/** `ImageActivity` in schemas.py. */
export type ImageActivity = {
  name: string;
  events: ImageEvent[];
  status: ImageRunStatus | null;
  /** Pass as `after` to read only what happens from here on. */
  cursor: string | null;
};

/** `ImageListing` in schemas.py. */
export type ImageListing = {
  directory: string;
  data_directory: string;
  images: ImageSummary[];
  last_viewed: string | null;
  unreadable: string[];
};

/** `PaneLayout` in schemas.py. */
export type PaneLayout = { size: number | null; open: boolean };

/** `AppLayout` in schemas.py. */
export type AppLayout = { images: PaneLayout; request: PaneLayout };

/** `ImagesView` in schemas.py: Your images as a file tree with columns, or as a grid of previews. */
export type ImagesView = "details" | "grid";

/** `AppSettings` in schemas.py. */
export type AppSettings = {
  theme: "system" | "light" | "dark";
  images_view: ImagesView;
  wide: AppLayout;
  medium: AppLayout;
};

/** `AppMethod` in schemas.py: an image model, or drawing an SVG. */
export type AppMethod = "model" | "svg";

/** `ImageMethodSetup` in schemas.py. */
export type MethodSetup = {
  /** Whether what it needs is installed and configured on this machine. */
  ready: boolean;
  /** What to set up, when it is not ready. */
  problem: string | null;
  /** The extensions the name of an image it makes can end in. */
  formats: string[];
};

/** The fields of `OpenAIImageMethod` in schemas.py that the view reads. */
export type OpenAIImageMethod = MethodSetup & {
  models: { id: string; label: string }[];
  default_model: string;
  qualities: string[];
  complexities: string[];
  backgrounds: string[];
  /** The images a request can send, counting the image being edited. */
  max_images: number;
  max_count: number;
  max_previews: number;
};

/** The fields of `IntelligenceModel` in schemas.py that the view reads. */
export type IntelligenceModel = {
  id: string;
  label: string;
  reasoning_efforts: string[];
};

/** The fields of `ChatGPTImageMethod` in schemas.py that the view reads. */
export type ChatGPTImageMethod = MethodSetup & {
  /** The Codex models that can carry the request. */
  models: IntelligenceModel[];
  default_model: string;
  default_reasoning_effort: string;
  /** The images a request can send, counting the image being edited and its marked copy. */
  max_images: number;
};

/** `ImageMethods` in schemas.py. */
export type ImageMethods = {
  openai: OpenAIImageMethod;
  chatgpt: ChatGPTImageMethod;
  svg: MethodSetup;
};

/** `AppImageRequest` in schemas.py: what was last picked for a request to an image model. */
export type AppImageRequest = {
  /** An OpenAI image model's id, or `chatgpt`; null for the default. */
  model: string | null;
  /** Width and height; null for the service's choice, on an edit the image's own size. */
  size: [number, number] | null;
  quality: string;
  /** The extension a new image's name ends in. */
  format: string;
  background: string;
  count: number;
  /** Null for the service's choice. */
  complexity: string | null;
  compression: number;
  /** The Codex model that carries a request to ChatGPT; null for the default. */
  codex_model: string | null;
  reasoning_effort: string | null;
};

/** `Mark` in schemas.py, as a request sends one: its points are fractions of the image from its top left. */
export type SentMark = {
  shape: "circle" | "box" | "arrow" | "sketch";
  points: [number, number][];
  /** For a sketch of several strokes, each stroke after the first. */
  strokes?: [number, number][][];
  color: string;
};

/** A reference as a request names it: a path the app offers, or the upload holding a file the view sent. */
export type SentReference = { path: string } | { upload: string };

/** `ReferenceEntry` in schemas.py: an image file the app offers as a reference. */
export type ReferenceEntry = {
  name: string;
  path: string;
  /** Null for a drawing, or a file that could not be read. */
  width: number | null;
  height: number | null;
};

/** `ReferenceLibrary` in schemas.py. */
export type ReferenceLibrary = {
  pinned: ReferenceEntry[];
  /** What requests sent from the app were given, newest first. */
  used: ReferenceEntry[];
};

/** `AppFolder` in schemas.py: a pinned folder, which lists its images in the app or opens the file dialog in it. */
export type AppFolder = { path: string; shows: "files" | "dialog" };

/** What guides a request besides its prompt. */
type RequestGuides = {
  references?: SentReference[];
  marks?: SentMark[];
};

/** What the request tools take, as `generate_openai_image` and `generate_chatgpt_image` in lib.py name them. */
export type ImageRequest =
  | {
      method: "openai";
      arguments: RequestGuides & {
        /** The upload holding the mask. */
        mask?: string;
        prompt: string;
        name: string;
        version?: string;
        model: string;
        size?: [number, number];
        quality: string;
        complexity?: string;
        background: string;
        compression?: number;
        count: number;
        previews: number;
      };
    }
  | {
      method: "chatgpt";
      arguments: RequestGuides & {
        prompt: string;
        name: string;
        version?: string;
        transparent: boolean;
        model?: string;
        reasoning_effort?: string;
      };
    };

/** `ImageRequestPreview` in schemas.py: what a request would send. */
export type ImageRequestPreview = {
  method: ImageMethod;
  name: string;
  /** Whether an image with that name exists, so the request edits it. */
  edits: boolean;
  /** The prompt as the image model receives it. */
  prompt: string;
  /** What the tool adds after the prompt as written; null when it adds nothing. */
  added: string | null;
  images: {
    role: "source" | "marked-copy" | "reference" | "marks" | "mask";
    path: string | null;
  }[];
  parameters: Record<string, string | number | boolean>;
};

/** `AppState` in schemas.py. */
export type AppState = {
  method: AppMethod;
  request: AppImageRequest;
  /** The folders closed in Your images, by their paths. */
  closed_folders: string[];
  /** The image files pinned as references, by their paths, newest first. */
  pins: string[];
  folders: AppFolder[];
};

// Deleting an image first stops a run working on it, which the server waits on for up to 15 seconds.
const DELETE_TIMEOUT_MS = 30_000;
// A run starts in a process of its own, and with ChatGPT an agent starts in that, before the tool answers.
const START_TIMEOUT_MS = 120_000;
// A window that asks the person for something stays open for as long as they take to answer it.
const DIALOG_TIMEOUT_MS = 3_600_000;

function textOf(result: CallToolResult): string {
  return result.content
    .flatMap((block) => (block.type === "text" ? [block.text] : []))
    .join("\n");
}

async function call(
  name: string,
  args: Record<string, unknown>,
  timeout?: number,
): Promise<CallToolResult> {
  const result = await app.callServerTool(
    { name, arguments: args },
    timeout ? { timeout } : undefined,
  );
  if (result.isError) {
    const failure = result.structuredContent as
      { reason?: string | null; image?: string | null } | undefined;
    throw new AppError(
      textOf(result) || `\`${name}\` failed.`,
      failure?.reason ?? null,
      failure?.image ?? null,
    );
  }
  return result;
}

async function structuredFrom(
  name: string,
  args: Record<string, unknown>,
  timeout?: number,
): Promise<Record<string, unknown>> {
  const result = await call(name, args, timeout);
  if (!result.structuredContent) {
    throw new AppError(
      `\`${name}\` returned nothing. Check that the server is Image Design.`,
    );
  }
  return result.structuredContent as Record<string, unknown>;
}

/** The images in the app's directory, in name order, and the one viewed last. */
export async function listImages(): Promise<ImageListing> {
  const structured = await structuredFrom(LIST_TOOL, {});
  if (!Array.isArray(structured.images)) {
    throw new AppError(
      `\`${LIST_TOOL}\` returned no images. Check that the server is this version of Image Design.`,
    );
  }
  return structured as ImageListing;
}

/** Record the image as the one the person is looking at, which the app opens on next time. */
export async function viewImage(name: string): Promise<ImageSummary> {
  return (await structuredFrom(VIEW_TOOL, { name })) as ImageSummary;
}

/** Rename the image, or move it to another folder of the directory. */
export async function moveImage(
  name: string,
  newName: string,
): Promise<ImageSummary> {
  return (await structuredFrom(MOVE_TOOL, {
    name,
    new_name: newName,
  })) as ImageSummary;
}

/** Delete the image's file and everything kept for it. */
export async function deleteImage(name: string): Promise<void> {
  await call(DELETE_TOOL, { name }, DELETE_TIMEOUT_MS);
}

/** Put an earlier version of the image back in its file. */
export async function restoreImageVersion(
  name: string,
  version: string,
): Promise<ImageSummary> {
  return (await structuredFrom(RESTORE_TOOL, {
    name,
    version,
  })) as ImageSummary;
}

/** What happened to the image, run by run; only what is new since `after`, the cursor of an earlier read. */
export async function readImageActivity(
  name: string,
  after: string | null,
): Promise<ImageActivity> {
  return (await structuredFrom(
    ACTIVITY_TOOL,
    after === null ? { name } : { name, after },
  )) as ImageActivity;
}

/** The ways of making an image, whether each is set up on this machine, and what each takes. */
export async function listImageMethods(): Promise<ImageMethods> {
  return (await structuredFrom(METHODS_TOOL, {})) as ImageMethods;
}

/** What a started request answers with. */
export type StartedRequest = {
  name: string;
  run_id: string;
  /** Where each reference it was given is offered from now, in order: an upload it took, from the run's own copy. */
  references: string[];
};

/** Start creating or editing an image. It answers once the run has started. */
export async function generateImage(
  request: ImageRequest,
): Promise<StartedRequest> {
  return (await structuredFrom(
    GENERATE_TOOLS[request.method],
    request.arguments,
    START_TIMEOUT_MS,
  )) as StartedRequest;
}

/** What the request would send, worked out by the library without sending it. */
export async function previewImageRequest(
  request: ImageRequest,
): Promise<ImageRequestPreview> {
  return (await structuredFrom(
    PREVIEW_TOOLS[request.method],
    request.arguments,
  )) as ImageRequestPreview;
}

/** Stop the run working on the image, whoever started it. */
export async function cancelImage(name: string): Promise<void> {
  await call(CANCEL_TOOL, { name });
}

async function readImage(prefix: string, path: string): Promise<string> {
  const uri = `${prefix}${path.split("/").map(encodeURIComponent).join("/")}`;
  const result = await app.readServerResource({ uri });
  const content = result.contents[0];
  if (!content || !("blob" in content)) {
    throw new AppError(`${uri} came back without its file.`);
  }
  return `data:${content.mimeType ?? "image/png"};base64,${content.blob}`;
}

/**
 * An image as a data URL: its file, or the version `version` kept for it; with `small`, a thumbnail of either. The
 * view's content security policy lets it load images from nowhere else.
 */
export function readImagePicture(
  name: string,
  version: string | null,
  small: boolean,
): Promise<string> {
  if (small) {
    return readImage(IMAGE_THUMBNAIL_PREFIX, `${version ?? FILE}/${name}`);
  }
  return version === null
    ? readImage(IMAGE_FILE_PREFIX, name)
    : readImage(IMAGE_VERSION_PREFIX, `${version}/${name}`);
}

/** An in-progress image of a run on the image, by the index its `preview` event has, as a data URL. */
export function readRunPreview(
  name: string,
  run: string,
  index: number,
): Promise<string> {
  return readImage(RUN_PREVIEW_PREFIX, `${run}/${index}/${name}`);
}

/** A small copy of an image the app offers as a reference, by its path on the machine the app runs on. */
export async function readReference(path: string): Promise<string> {
  const uri = `${REFERENCE_PREFIX}${encodeURIComponent(path)}`;
  const result = await app.readServerResource({ uri });
  const content = result.contents[0];
  if (!content || !("blob" in content)) {
    throw new AppError(`${uri} came back without its file.`);
  }
  return `data:${content.mimeType ?? "image/webp"};base64,${content.blob}`;
}

/** Send a piece of a file for a request to take, and learn how much of the file has arrived. */
export async function uploadPiece(
  upload: string,
  name: string,
  offset: number,
  data: string,
): Promise<number> {
  const structured = await structuredFrom(UPLOAD_TOOL, {
    upload,
    name,
    offset,
    data,
  });
  return structured.received as number;
}

/** What the person pinned, and what requests sent from the app were given before. */
export async function readReferenceLibrary(): Promise<ReferenceLibrary> {
  return (await structuredFrom(LIBRARY_TOOL, {})) as ReferenceLibrary;
}

/** The images in a folder pinned to show its files. */
export async function listReferenceFolder(
  path: string,
): Promise<ReferenceEntry[]> {
  const structured = await structuredFrom(FOLDER_TOOL, { path });
  return structured.entries as ReferenceEntry[];
}

/** Ask the person for image files in their platform's file dialog, opened in `folder` when given. */
export async function chooseReferenceFiles(
  folder: string | null,
): Promise<ReferenceEntry[]> {
  const structured = await structuredFrom(
    CHOOSE_FILES_TOOL,
    folder === null ? {} : { folder },
    DIALOG_TIMEOUT_MS,
  );
  return structured.entries as ReferenceEntry[];
}

/** Ask the person for a folder to pin in their platform's folder dialog; null when they cancel. */
export async function chooseReferenceFolder(): Promise<string | null> {
  const structured = await structuredFrom(
    CHOOSE_FOLDER_TOOL,
    {},
    DIALOG_TIMEOUT_MS,
  );
  return structured.path as string | null;
}

/** Keep an uploaded image with the app's state, so it can be pinned. */
export async function keepReference(upload: string): Promise<ReferenceEntry> {
  return (await structuredFrom(KEEP_TOOL, { upload })) as ReferenceEntry;
}

/** `OpenAIKeyStatus` in schemas.py: where the OpenAI API key comes from. The key itself never reaches the view. */
export type OpenAIKeyStatus = {
  /** What requests are sent with: the environment's key, which wins, or the saved one; null for no key. */
  source: "environment" | "saved" | null;
  /** Whether a key is saved, also when the environment's is the one used. */
  saved: boolean;
};

export async function readOpenAIKey(): Promise<OpenAIKeyStatus> {
  return (await structuredFrom(READ_KEY_TOOL, {})) as OpenAIKeyStatus;
}

/**
 * Have the person type their key into a window on the machine the server runs on, which saves it there. It answers
 * once they have, with whether they entered one.
 */
export async function enterOpenAIKey(): Promise<
  OpenAIKeyStatus & { entered: boolean }
> {
  return (await structuredFrom(
    ENTER_KEY_TOOL,
    {},
    DIALOG_TIMEOUT_MS,
  )) as OpenAIKeyStatus & { entered: boolean };
}

/** Forget the saved key. */
export async function clearOpenAIKey(): Promise<OpenAIKeyStatus> {
  return (await structuredFrom(CLEAR_KEY_TOOL, {})) as OpenAIKeyStatus;
}

/** How the person set up the app, the same in every directory. */
export async function readAppSettings(): Promise<AppSettings> {
  return (await structuredFrom(READ_SETTINGS_TOOL, {})) as AppSettings;
}

/** Keep the app's settings for the person, replacing the ones kept before. */
export async function saveAppSettings(
  settings: AppSettings,
): Promise<AppSettings> {
  return (await structuredFrom(SAVE_SETTINGS_TOOL, {
    settings,
  })) as AppSettings;
}

/** What the person last picked in the app for the images in its directory. */
export async function readAppState(): Promise<AppState> {
  return (await structuredFrom(READ_STATE_TOOL, {})) as AppState;
}

/** Keep what the person picked for the images in the app's directory, replacing what was kept before. */
export async function saveAppState(state: AppState): Promise<AppState> {
  return (await structuredFrom(SAVE_STATE_TOOL, { state })) as AppState;
}
