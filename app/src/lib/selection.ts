import { movedPath } from "@/lib/paths";

/**
 * What is selected in a list, as a file manager keeps it. Every function here takes the paths of the list in the
 * order they show.
 */
export type Selection = {
  paths: ReadonlySet<string>;
  /** Where a Shift click, or Shift with an arrow, measures its run from. */
  anchor: string | null;
  /** The one the keys move from. */
  lead: string | null;
};

export const NOTHING: Selection = {
  paths: new Set(),
  anchor: null,
  lead: null,
};

/** One alone, as after a click. */
export function only(path: string): Selection {
  return { paths: new Set([path]), anchor: path, lead: path };
}

/** One added, or taken out when it is in, as after a click with Ctrl. */
export function toggled(selection: Selection, path: string): Selection {
  const paths = new Set(selection.paths);
  if (!paths.delete(path)) {
    paths.add(path);
  }
  return { paths, anchor: path, lead: path };
}

/**
 * The run from the anchor to `path`, as after a click with Shift. With `add` it joins what is selected, as with Ctrl
 * held too.
 */
export function ranged(
  selection: Selection,
  order: string[],
  path: string,
  add = false,
): Selection {
  const anchor =
    selection.anchor !== null && order.includes(selection.anchor)
      ? selection.anchor
      : path;
  const [start, end] = [order.indexOf(anchor), order.indexOf(path)].sort(
    (a, b) => a - b,
  );
  const run = order.slice(start, end + 1);
  return {
    paths: new Set(add ? [...selection.paths, ...run] : run),
    anchor,
    lead: path,
  };
}

/** Everything in the list. */
export function all(selection: Selection, order: string[]): Selection {
  return {
    paths: new Set(order),
    anchor: selection.anchor ?? order[0] ?? null,
    lead: selection.lead ?? order.at(-1) ?? null,
  };
}

/** What a box drawn over the list touches, with what was selected before it when the box adds. */
export function boxed(before: Selection | null, touched: string[]): Selection {
  return {
    paths: new Set([...(before?.paths ?? []), ...touched]),
    anchor: touched[0] ?? before?.anchor ?? null,
    lead: touched.at(-1) ?? before?.lead ?? null,
  };
}

/** The one `by` places from the lead, stopping at the ends; the first or the last when there is no lead. */
export function stepped(
  selection: Selection,
  order: string[],
  by: number,
): string | null {
  if (order.length === 0) {
    return null;
  }
  const from = selection.lead === null ? -1 : order.indexOf(selection.lead);
  if (from < 0) {
    return by > 0 ? order[0] : order[order.length - 1];
  }
  return order[Math.min(order.length - 1, Math.max(0, from + by))];
}

/** The selection without what the list no longer shows. */
export function showing(selection: Selection, order: string[]): Selection {
  const shown = new Set(order);
  const kept = (path: string | null) =>
    path !== null && shown.has(path) ? path : null;
  if (
    [...selection.paths].every((path) => shown.has(path)) &&
    kept(selection.anchor) === selection.anchor &&
    kept(selection.lead) === selection.lead
  ) {
    return selection;
  }
  return {
    paths: new Set([...selection.paths].filter((path) => shown.has(path))),
    anchor: kept(selection.anchor),
    lead: kept(selection.lead),
  };
}

/** The selection once `from` has become `to`, so what was selected stays selected under its new path. */
export function moved(
  selection: Selection,
  from: string,
  to: string,
): Selection {
  const after = (path: string | null) =>
    path === null ? null : movedPath(path, from, to);
  return {
    paths: new Set(
      [...selection.paths].map((path) => movedPath(path, from, to)),
    ),
    anchor: after(selection.anchor),
    lead: after(selection.lead),
  };
}
