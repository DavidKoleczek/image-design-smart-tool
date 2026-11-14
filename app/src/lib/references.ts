import { useEffect, useState, useSyncExternalStore } from "react";

import {
  keepReference,
  readReference,
  uploadPiece,
  type ReferenceEntry,
  type SentReference,
} from "@/lib/api";
import { maskPng, maskRevision } from "@/lib/canvas";
import { describe } from "@/lib/errors";
import { updateAppState } from "@/lib/state";

/** An image a request sends along without editing it. */
export type Reference = {
  /** Its own in the list it is in. */
  id: string;
  name: string;
  /** For a file on the machine the app runs on that the app offers: its path there. */
  path: string | null;
  /** For a file dropped or pasted into the view: the upload that holds it. */
  upload: string | null;
  /** For an upload: a small copy made here, since the server has none to give. */
  thumb: string | null;
  /** Whether an upload has arrived; a path is always ready. */
  state: "ready" | "uploading" | "failed";
};

// How much of a file goes up in one call, before base64 makes it a third longer.
const PIECE_BYTES = 2 * 1024 * 1024;
const THUMB_EDGE = 128;
const THUMBS_KEPT = 400;
const NONE: Reference[] = [];

const listeners = new Set<() => void>();
// The references of the request being written for each image, and for the new image, kept for the session.
const lists = new Map<string, Reference[]>();
const thumbs = new Map<string, Promise<string>>();
let made = 0;

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function set(key: string, references: Reference[]) {
  if (references.length === 0) {
    lists.delete(key);
  } else {
    lists.set(key, references);
  }
  emit();
}

function newId(): string {
  made += 1;
  return `reference-${made}`;
}

/** An id for an upload, which the server takes as 16 to 64 hex digits. */
export function newUploadId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

export function useReferences(key: string): Reference[] {
  return useSyncExternalStore(subscribe, () => lists.get(key) ?? NONE);
}

export function referencesOf(key: string): Reference[] {
  return lists.get(key) ?? NONE;
}

/** The entry as a reference. */
function ofEntry(entry: { name: string; path: string }): Reference {
  return {
    id: newId(),
    name: entry.name,
    path: entry.path,
    upload: null,
    thumb: null,
    state: "ready",
  };
}

/** Add files the app offers to a request's references, up to `room` in all, each path once. */
export function addEntries(
  key: string,
  entries: { name: string; path: string }[],
  room: number,
) {
  const current = referencesOf(key);
  const fresh = entries.filter(
    (entry, index) =>
      !current.some((reference) => reference.path === entry.path) &&
      entries.findIndex((other) => other.path === entry.path) === index,
  );
  const taken = fresh.slice(0, Math.max(0, room - current.length));
  if (taken.length > 0) {
    set(key, [...current, ...taken.map(ofEntry)]);
  }
}

/** Take a file the app offers out of a request's references, or put it in when it is not there. */
export function toggleEntry(
  key: string,
  entry: { name: string; path: string },
  room: number,
) {
  const current = referencesOf(key);
  if (current.some((reference) => reference.path === entry.path)) {
    set(
      key,
      current.filter((reference) => reference.path !== entry.path),
    );
  } else {
    addEntries(key, [entry], room);
  }
}

export function removeReference(key: string, id: string) {
  set(
    key,
    referencesOf(key).filter((reference) => reference.id !== id),
  );
}

/** Move a reference to another place in the order, which is how the prompt names them. */
export function moveReference(key: string, id: string, index: number) {
  const references = referencesOf(key).slice();
  const at = references.findIndex((reference) => reference.id === id);
  const target = Math.min(references.length - 1, Math.max(0, index));
  if (at < 0 || at === target) {
    return;
  }
  references.splice(target, 0, references.splice(at, 1)[0]);
  set(key, references);
}

export function clearReferences(key: string) {
  set(key, []);
}

/** Give a request's references to the name its image now has. */
export function moveReferences(from: string, to: string) {
  const references = lists.get(from);
  if (references) {
    lists.delete(from);
    set(to, references);
  }
}

/** Change a reference wherever it is listed, since an upload ends long after it was added. */
function changeReference(id: string, change: Partial<Reference>) {
  for (const [key, references] of lists) {
    if (references.some((reference) => reference.id === id)) {
      set(
        key,
        references.map((reference) =>
          reference.id === id ? { ...reference, ...change } : reference,
        ),
      );
      return;
    }
  }
}

/**
 * Once a request has started, point each upload it took at where the server offers it from now, which is the run's
 * own copy: the upload itself is cleared.
 */
export function settleReferences(
  key: string,
  sent: Reference[],
  paths: string[],
) {
  if (sent.length !== paths.length) {
    return;
  }
  const now = new Map(
    sent.map((reference, index) => [reference.id, paths[index]]),
  );
  set(
    key,
    referencesOf(key).map((reference) =>
      reference.upload !== null && now.has(reference.id)
        ? { ...reference, upload: null, path: now.get(reference.id) ?? null }
        : reference,
    ),
  );
}

/** The references as a request names them. */
export function sentReferences(references: Reference[]): SentReference[] {
  return references.map((reference) =>
    reference.upload !== null
      ? { upload: reference.upload }
      : { path: reference.path ?? "" },
  );
}

function base64(bytes: Uint8Array): string {
  let binary = "";
  // In runs, since a call takes only so many arguments.
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(binary);
}

/** Send a file up in pieces under `upload`. A piece that fails is sent once more before the upload gives up. */
export async function uploadFile(
  upload: string,
  name: string,
  bytes: Uint8Array,
): Promise<void> {
  for (let offset = 0; offset < bytes.length; offset += PIECE_BYTES) {
    const piece = base64(bytes.subarray(offset, offset + PIECE_BYTES));
    try {
      await uploadPiece(upload, name, offset, piece);
    } catch {
      await uploadPiece(upload, name, offset, piece);
    }
  }
}

// The mask last sent up for each image, and which painting of it that was, so the same one is not sent twice.
const sentMasks = new Map<string, { revision: number; upload: string }>();

/**
 * Send up the mask painted on the image named `name`, which is `width` by `height`, and return the upload that holds
 * it with the mask itself as a data URL; null when nothing is painted.
 */
export async function uploadMask(
  name: string,
  width: number,
  height: number,
): Promise<{ upload: string; url: string } | null> {
  const url = maskPng(name, width, height);
  if (url === null) {
    return null;
  }
  const revision = maskRevision(name);
  const sent = sentMasks.get(name);
  if (sent && sent.revision === revision) {
    return { upload: sent.upload, url };
  }
  const upload = newUploadId();
  await uploadFile(upload, "mask.png", dataBytes(url));
  sentMasks.set(name, { revision, upload });
  return { upload, url };
}

/** The bytes of a `data:` URL's base64. */
export function dataBytes(url: string): Uint8Array {
  const binary = atob(url.slice(url.indexOf(",") + 1));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

/** A small copy of an image file, as a data URL, since the view can show nothing from a `blob:` URL. */
async function thumbOf(file: File): Promise<string | null> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(
      1,
      THUMB_EDGE / Math.max(bitmap.width, bitmap.height),
    );
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas
      .getContext("2d")
      ?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return canvas.toDataURL("image/png");
  } catch {
    return null;
  }
}

function named(file: File): string {
  const name = file.name.replaceAll("\\", "/").split("/").pop() ?? "";
  return name.trim() || `pasted.${file.type.split("/")[1] ?? "png"}`;
}

/**
 * Add image files dropped or pasted into the view to a request's references, up to `room` in all. Each shows at once
 * and goes up in the background.
 */
export function addFiles(key: string, files: File[], room: number) {
  const images = files.filter((file) => file.type.startsWith("image/"));
  const taken = images.slice(0, Math.max(0, room - referencesOf(key).length));
  for (const file of taken) {
    const reference: Reference = {
      id: newId(),
      name: named(file),
      path: null,
      upload: newUploadId(),
      thumb: null,
      state: "uploading",
    };
    set(key, [...referencesOf(key), reference]);
    void thumbOf(file).then(
      (thumb) => thumb && changeReference(reference.id, { thumb }),
    );
    void file
      .arrayBuffer()
      .then((buffer) =>
        uploadFile(
          reference.upload as string,
          reference.name,
          new Uint8Array(buffer),
        ),
      )
      .then(
        () => changeReference(reference.id, { state: "ready" }),
        () => changeReference(reference.id, { state: "failed" }),
      );
  }
}

/** The image files of a drop or a paste. */
export function imageFiles(transfer: DataTransfer | null): File[] {
  return [...(transfer?.files ?? [])].filter((file) =>
    file.type.startsWith("image/"),
  );
}

function setPins(change: (pins: string[]) => string[]) {
  updateAppState((current) => ({ ...current, pins: change(current.pins) }));
}

/** Pin a file the app offers, so it is found under Pinned, or unpin it. */
export function togglePin(path: string) {
  setPins((pins) =>
    pins.includes(path) ? pins.filter((pin) => pin !== path) : [path, ...pins],
  );
}

/**
 * Pin a reference, or unpin it. An upload has no path to pin, so the server first keeps a copy with the app's state,
 * and the reference is that copy from then on.
 */
export async function togglePinned(reference: Reference): Promise<void> {
  if (reference.path !== null) {
    togglePin(reference.path);
    return;
  }
  if (reference.upload === null || reference.state !== "ready") {
    return;
  }
  const kept = await keepReference(reference.upload);
  rememberEntries([kept]);
  setPins((pins) => [kept.path, ...pins]);
  changeReference(reference.id, { path: kept.path, upload: null });
}

// What is known of each file the app offered, by its path, so a pin shows its name and size without asking again.
const known = new Map<string, ReferenceEntry>();

export function rememberEntries(entries: ReferenceEntry[]) {
  for (const entry of entries) {
    known.set(entry.path, entry);
  }
}

/** The last part of a path on the machine the app runs on, whichever way its slashes lean. */
export function fileName(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, "");
  return trimmed.slice(
    Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\")) + 1,
  );
}

/** The file at `path` as the app offered it, or by its name alone when it was never listed here. */
export function entryOf(path: string): ReferenceEntry {
  return (
    known.get(path) ?? {
      name: fileName(path),
      path,
      width: null,
      height: null,
    }
  );
}

function readThumb(path: string): Promise<string> {
  let reading = thumbs.get(path);
  if (!reading) {
    if (thumbs.size >= THUMBS_KEPT) {
      thumbs.clear();
    }
    reading = readReference(path);
    thumbs.set(path, reading);
    reading.catch(() => thumbs.delete(path));
  }
  return reading;
}

/** A small copy of the file at `path` that the app offers as a reference, as a data URL, once it is read. */
export function useThumb(path: string | null): {
  url: string | null;
  error: string | null;
} {
  const [read, setRead] = useState<{
    path: string;
    url: string | null;
    error: string | null;
  } | null>(null);
  useEffect(() => {
    if (path === null) {
      return;
    }
    let current = true;
    readThumb(path).then(
      (url) => current && setRead({ path, url, error: null }),
      (cause: unknown) =>
        current && setRead({ path, url: null, error: describe(cause) }),
    );
    return () => {
      current = false;
    };
  }, [path]);
  return read && read.path === path
    ? { url: read.url, error: read.error }
    : { url: null, error: null };
}
