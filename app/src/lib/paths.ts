/** A path's last part: a file's or a folder's name without the folders it is in. */
export function baseName(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

/** The folder a path is in, "" for the top. */
export function folderOf(path: string): string {
  return path.slice(0, Math.max(0, path.lastIndexOf("/")));
}

/** The path of `name` in `folder`, which is "" for the top. */
export function joined(folder: string, name: string): string {
  return folder ? `${folder}/${name}` : name;
}

/** Whether `path` is `folder` or anything inside it. */
export function within(path: string, folder: string, separator = "/"): boolean {
  return path === folder || path.startsWith(folder + separator);
}

/** Where `path` is once `from` has become `to`: moved with it when it is `from` or inside it, and itself otherwise. */
export function movedPath(
  path: string,
  from: string,
  to: string,
  separator = "/",
): string {
  if (path === from) {
    return to;
  }
  return path.startsWith(from + separator)
    ? to + path.slice(from.length)
    : path;
}

/** A file's name as what a rename changes and the extension it keeps, which has its dot. */
export function splitName(name: string): [string, string] {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? [name.slice(0, dot), name.slice(dot)] : [name, ""];
}

/** Names in the order a file manager lists them: whatever their case, and `(2)` before `(10)`. */
export function byName(a: string, b: string): number {
  return a.localeCompare(b, undefined, { sensitivity: "base", numeric: true });
}

/**
 * `path`, or when it is taken the first of `name (2)`, `name (3)`, and so on that is not, as `free_name` in the
 * library picks it. The number goes before a file's extension, as in `cactus (2).png`.
 */
export function freeName(
  path: string,
  folder: boolean,
  taken: (path: string) => boolean,
): string {
  const [stem, extension] = folder
    ? [baseName(path), ""]
    : splitName(baseName(path));
  let free = path;
  for (let number = 2; taken(free); number += 1) {
    free = joined(folderOf(path), `${stem} (${number})${extension}`);
  }
  return free;
}

const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)/i;

/** Why a file or a folder cannot be given the name, on Windows or anywhere else; null when it can. */
export function nameProblem(name: string): string | null {
  if (/[\\/]/.test(name)) {
    return "A name can't have a slash in it.";
  }
  // eslint-disable-next-line no-control-regex -- the characters below a space are among those Windows refuses.
  if (/[<>:"|?*\u0000-\u001f]/.test(name)) {
    return "A name can't have any of < > : \" | ? * in it.";
  }
  if (name.startsWith(".")) {
    return "A name can't start with a dot, which would hide it.";
  }
  if (/[. ]$/.test(name)) {
    return "A name can't end with a dot or a space.";
  }
  if (RESERVED.test(name)) {
    return "Windows keeps that name for itself.";
  }
  return null;
}

// The extensions an image's name can end in, as `KEPT_SUFFIXES` in the library, and `.jpeg`, which is typed for one.
const IMAGE_EXTENSION = /\.(png|jpe?g|webp|gif|svg)$/i;

/**
 * Why a name typed beside the extension it ends in cannot be given, when it ends in an image's extension itself, which
 * would then come before that one; null when it can.
 */
export function extensionProblem(
  typed: string,
  extension: string,
): string | null {
  const ending = IMAGE_EXTENSION.exec(typed.trim())?.[0];
  return ending === undefined
    ? null
    : `Leave out ${ending}. The name already ends in ${extension}.`;
}

/**
 * Why a new image cannot be given the path typed for it, which may name folders, before the extension it ends in;
 * null when it can.
 */
export function typedProblem(typed: string, extension: string): string | null {
  return (
    extensionProblem(typed, extension) ??
    `${typed.trim()}${extension}`
      .split("/")
      .map((part) => nameProblem(part))
      .find((problem) => problem !== null) ??
    null
  );
}

/** The name a copy has beside what it is a copy of, as in `cactus - Copy.png`. */
export function copyName(name: string, folder: boolean): string {
  const [stem, extension] = folder ? [name, ""] : splitName(name);
  return `${stem} - Copy${extension}`;
}

/** The paths that are not inside another of them, so a folder stands for everything in it. */
export function topmost(paths: string[]): string[] {
  return paths.filter(
    (path) => !paths.some((other) => other !== path && within(path, other)),
  );
}
