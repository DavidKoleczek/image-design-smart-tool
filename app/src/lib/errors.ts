/** A failure from the server, with which one it was when the library named it, and the image it concerns. */
export class AppError extends Error {
  readonly reason: string | null;
  readonly image: string | null;

  constructor(
    message: string,
    reason: string | null = null,
    image: string | null = null,
  ) {
    super(message);
    this.reason = reason;
    this.image = image;
  }
}

/**
 * The library's message names commands and arguments for an agent, so each failure it names is worded here for the
 * person, in the app's terms. One without a wording here shows the library's message.
 */
function worded(error: AppError): string | null {
  switch (error.reason) {
    case "no-such-image":
      return "That image is no longer there. It may have been moved or deleted outside the app.";
    case "no-such-version":
      return "That version is no longer kept for this image.";
    case "invalid-name":
      return "That name can't be used. Give a path inside the directory that keeps the image's extension, such as concepts/cactus.png.";
    case "name-in-use":
      return "Another image already has that name. Choose another, or delete that image first.";
    case "already-running":
      return "A request is still working on this image. Wait for it to end, or stop it first.";
    case "not-running":
      return "No request is working on this image any more.";
    case "bad-settings":
      return "Those settings couldn't be saved. Reset the layout, or reload the app and try again.";
    case "bad-state":
      return "What you picked couldn't be saved. Reload the app and try again.";
    default:
      return null;
  }
}

/** What went wrong, for the person. */
export function describe(cause: unknown): string {
  if (cause instanceof AppError) {
    return worded(cause) ?? cause.message;
  }
  return cause instanceof Error ? cause.message : String(cause);
}

/** How a run that made no image ended, for the person. The library's own words stand for a failure it explains. */
export function describeEnding(
  status: "failed" | "cancelled" | "timed-out",
  error: string | null,
): string {
  if (status === "cancelled") {
    return "Stopped before it finished.";
  }
  if (status === "timed-out") {
    return "The request took too long and was stopped. It may still have been billed, or counted against a plan.";
  }
  return error ?? "The request failed without saying why.";
}
