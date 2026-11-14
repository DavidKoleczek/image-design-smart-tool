type Follower = (from: string, to: string) => void;

const followers = new Set<Follower>();

/**
 * Have `follower` called each time an image or a folder comes to have another name, so what it keeps by the name
 * goes with it. Both names are paths in the directory, and anything inside a folder moves with the folder. Returns
 * what stops it.
 */
export function onRenamed(follower: Follower): () => void {
  followers.add(follower);
  return () => {
    followers.delete(follower);
  };
}

/**
 * Say that what was at `from` in the directory is at `to` now, whoever moved it, so everything the view keeps by an
 * image's name follows it there.
 */
export function renamed(from: string, to: string) {
  if (from === to) {
    return;
  }
  for (const follower of followers) {
    follower(from, to);
  }
}

/** Give what `kept` holds under each key to the key `after` makes of it. Says whether any key changed. */
export function rekey<Value>(
  kept: Map<string, Value>,
  after: (key: string) => string,
): boolean {
  const moving = [...kept].filter(([key]) => after(key) !== key);
  for (const [key] of moving) {
    kept.delete(key);
  }
  for (const [key, value] of moving) {
    kept.set(after(key), value);
  }
  return moving.length > 0;
}

const leavers = new Set<(name: string) => void>();

/** Have `follower` called with the name of each image that is deleted, whoever deleted it. Returns what stops it. */
export function onGone(follower: (name: string) => void): () => void {
  leavers.add(follower);
  return () => {
    leavers.delete(follower);
  };
}

/** Say that the image named `name` is no more, so nothing kept by its name is there for a later image of that name. */
export function gone(name: string) {
  for (const follower of leavers) {
    follower(name);
  }
}
