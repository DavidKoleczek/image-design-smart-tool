import { uploadPiece } from "@/lib/api";

// How much of a file goes up in one call, before base64 makes it a third longer.
const PIECE_BYTES = 2 * 1024 * 1024;
const THUMB_EDGE = 128;

/** An id for an upload, which the server takes as 16 to 64 hex digits. */
export function newUploadId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
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

/** A small copy of an image file, as a data URL, since the view can show nothing from a `blob:` URL. */
export async function thumbOf(file: File): Promise<string | null> {
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
