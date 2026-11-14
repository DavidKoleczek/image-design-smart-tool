import type { CallToolResult } from "@modelcontextprotocol/client";

import { AppError } from "@/lib/errors";
import { app } from "@/lib/host";

const LIST_TOOL = "list_images";
const VIEW_TOOL = "view_image";
const MOVE_TOOL = "move_image";
const DELETE_TOOL = "delete_image";
const RESTORE_TOOL = "restore_image_version";
const ACTIVITY_TOOL = "read_image_activity";
const READ_SETTINGS_TOOL = "read_app_settings";
const SAVE_SETTINGS_TOOL = "save_app_settings";
const READ_STATE_TOOL = "read_app_state";
const SAVE_STATE_TOOL = "save_app_state";
const IMAGE_FILE_PREFIX = "image-design://images/";
const IMAGE_VERSION_PREFIX = "image-design://versions/";
const IMAGE_THUMBNAIL_PREFIX = "image-design://thumbnails/";
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
  /** ISO 8601. */
  started: string;
};

/** The fields of `ImageSummary` in schemas.py that the view reads. */
export type ImageSummary = {
  /** The image's path in the directory, with forward slashes. */
  name: string;
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

/** `AppState` in schemas.py. */
export type AppState = {
  method: AppMethod;
  /** The folders closed in Your images, by their paths. */
  closed_folders: string[];
};

// Deleting an image first stops a run working on it, which the server waits on for up to 15 seconds.
const DELETE_TIMEOUT_MS = 30_000;

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
