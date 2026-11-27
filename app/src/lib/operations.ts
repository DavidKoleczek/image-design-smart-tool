import { movedPath } from "@/lib/paths";

/**
 * A change to what is where, by paths: something renamed or moved, a folder made, a file copied, a file brought in
 * from outside, which `source` names for whoever makes the change, or something deleted.
 */
export type Change =
  | { kind: "move"; from: string; to: string; folder: boolean }
  | { kind: "folder"; path: string }
  | { kind: "copy"; from: string; to: string }
  | { kind: "add"; path: string; source: string }
  | { kind: "delete"; path: string; folder: boolean };

/** Something that could not be done, and why: a change, or what `what` says of something done outside the queue. */
export type Failure = { why: string } & ({ change: Change } | { what: string });

// A failure with the run of changes it was in, so that only a later run going well clears it.
type Kept = Failure & { run: number };

type Operation = {
  id: number;
  change: Change;
  /** The last listing asked for when the change was made, so a later one is known to have it; null until then. */
  made: number | null;
};

/** Where `path` is once the changes are made, in order. */
export function pathAfter(path: string, changes: Change[]): string {
  return changes.reduce(
    (at, change) =>
      change.kind === "move" ? movedPath(at, change.from, change.to) : at,
    path,
  );
}

function retargeted(change: Change, from: string, to: string): Change {
  return change.kind === "move" || change.kind === "copy"
    ? {
        ...change,
        from: movedPath(change.from, from, to),
        to: movedPath(change.to, from, to),
      }
    : { ...change, path: movedPath(change.path, from, to) };
}

/** Where a change puts what it moves or makes; null for one that makes nothing. */
function landing(change: Change): string | null {
  switch (change.kind) {
    case "move":
    case "copy":
      return change.to;
    case "folder":
    case "add":
      return change.path;
    case "delete":
      return null;
  }
}

function landed(change: Change, at: string): Change {
  switch (change.kind) {
    case "move":
    case "copy":
      return { ...change, to: at };
    case "folder":
    case "add":
      return { ...change, path: at };
    case "delete":
      return change;
  }
}

/**
 * Changes that show before the server has made them. Each shows as soon as it is added, and they are made one at a
 * time in the order they were added. One that fails is undone and kept as a failure to report.
 *
 * A listing read from the server may be from before a change or after it, so each listing is asked for through
 * `asking`, and `over` gives the changes that listing does not have yet.
 */
export function changeQueue(options: {
  /**
   * Make the change, and return the path the server gave what it moved or made, which may not be the one asked for.
   * What a delete returns is not read.
   */
  run: (change: Change) => Promise<string>;
  /** Called as a path changes: when a move shows, when the server gave another path, and backwards on a failure. */
  onMoved: (from: string, to: string) => void;
  describe: (cause: unknown) => string;
}) {
  const listeners = new Set<() => void>();
  const drained = new Set<() => void>();
  let operations: Operation[] = [];
  let failures: Kept[] = [];
  let added = 0;
  // Counts the times changes started being made with none under way.
  let runs = 0;
  let asked = 0;
  let working: Promise<void> | null = null;
  // Counts the times the changes were forgotten, so what a change under way then comes to is dropped with it.
  let generation = 0;

  const emit = () => {
    for (const listener of listeners) {
      listener();
    }
  };

  // What waits behind a change names things by where that change put them, so it follows when that turns out wrong.
  const retarget = (from: string, to: string) => {
    operations = operations.map((each) =>
      each.made === null
        ? { ...each, change: retargeted(each.change, from, to) }
        : each,
    );
  };

  const make = async (operation: Operation) => {
    const { change } = operation;
    const shown = landing(change);
    const made = generation;
    try {
      const given = await options.run(change);
      if (made !== generation) {
        return;
      }
      operations = operations.map((each) =>
        each.id === operation.id
          ? { ...each, made: asked, change: landed(change, given) }
          : each,
      );
      failures = failures.filter((each) => each.run === runs);
      if (shown !== null && given !== shown) {
        retarget(shown, given);
        options.onMoved(shown, given);
      }
    } catch (cause) {
      if (made !== generation) {
        return;
      }
      operations = operations.filter((each) => each.id !== operation.id);
      failures = [
        ...failures,
        { change, why: options.describe(cause), run: runs },
      ];
      if (change.kind === "move") {
        retarget(change.to, change.from);
        options.onMoved(change.to, change.from);
      }
    }
    emit();
  };

  const work = async () => {
    for (;;) {
      const next = operations.find((each) => each.made === null);
      if (!next) {
        break;
      }
      await make(next);
    }
    working = null;
    for (const listener of drained) {
      listener();
    }
  };

  return {
    /** Show the change now, and make it once the ones before it are made. */
    add(change: Change) {
      added += 1;
      operations = [...operations, { id: added, change, made: null }];
      if (change.kind === "move") {
        options.onMoved(change.from, change.to);
      }
      emit();
      if (working === null) {
        runs += 1;
        working = work();
      }
    },
    /** Resolves once every change added so far is made or undone. */
    idle(): Promise<void> {
      return working ?? Promise.resolve();
    },
    /** Call before asking the server for a listing. What it returns tells that listing from the others. */
    asking(): number {
      asked += 1;
      return asked;
    },
    /** The changes to apply to the listing that `asking` returned `listing` for, since it may not have them. */
    over(listing: number): Change[] {
      return operations
        .filter((each) => each.made === null || listing <= each.made)
        .map((each) => each.change);
    },
    /** Say that a listing is the one showing, so the changes it has are forgotten. */
    seen(listing: number) {
      operations = operations.filter(
        (each) => each.made === null || listing <= each.made,
      );
    },
    /** What could not be made, until a later change is made or they are dismissed. */
    failures: (): Failure[] => failures,
    /** Keep a failure of something done outside the queue, to be told with the others. */
    report(what: string, why: string) {
      failures = [...failures, { what, why, run: runs }];
      emit();
    },
    dismiss() {
      failures = [];
      emit();
    },
    /**
     * Drop every change not yet made and every failure, as once what they name is no longer what shows. One under way
     * goes on at the server, and what it comes to is dropped.
     */
    forget() {
      generation += 1;
      operations = [];
      failures = [];
      emit();
    },
    /** Have `listener` called once every change is made, when the server has what shows. */
    onDrained(listener: () => void) {
      drained.add(listener);
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
