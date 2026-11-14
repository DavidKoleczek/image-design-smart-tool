import { useSyncExternalStore } from "react";

import type { IconName } from "@/components/ui/icon";
import type {
  ImageEvent,
  ImageRunStatus,
  ImageSummary,
  ImageUsage,
} from "@/lib/api";
import { MARK_COLORS, type MarkColor } from "@/lib/marks";
import type { RunFacts, Runs } from "@/lib/runs";

const IMAGE = /\.(png|jpe?g|gif|webp)$/i;
// The command that builds a drawing, which reads better as what it makes than as the command.
const BUILD = /svg_image\.build/;
const REFERENCE = /(?:^|\/)reference-(\d+)\.\w+$/;
const APP = "app";

/** A tool's verb for done and for under way, and its icon, by the name the agent gives the tool. */
const TOOLS: Record<string, { done: string; doing: string; icon: IconName }> = {
  Bash: { done: "Ran", doing: "Running", icon: "terminal" },
  Read: { done: "Read", doing: "Reading", icon: "file" },
  Edit: { done: "Edited", doing: "Editing", icon: "file-edit" },
  MultiEdit: { done: "Edited", doing: "Editing", icon: "file-edit" },
  Write: { done: "Wrote", doing: "Writing", icon: "file-edit" },
  Glob: { done: "Searched", doing: "Searching", icon: "search" },
  Grep: { done: "Searched", doing: "Searching", icon: "search" },
  commandExecution: { done: "Ran", doing: "Running", icon: "terminal" },
  fileChange: { done: "Edited", doing: "Editing", icon: "file-edit" },
  webSearch: { done: "Searched", doing: "Searching", icon: "search" },
};
const LOOK = { done: "Looked at", doing: "Looking at", icon: "image" as const };
const BUILT = { done: "Built", doing: "Building", icon: "terminal" as const };
// The arguments that name what a call works on, in the order they are looked for.
const TARGET_ARGUMENTS = [
  "file_path",
  "path",
  "command",
  "pattern",
  "query",
  "url",
  "description",
  "prompt",
];

export type CallState = "running" | "done" | "failed" | "unfinished";

/**
 * One step as a row shows it: a plain verb, what it worked on, and how it went. A tool call, with what it was called
 * with and what came back; or a stretch of reasoning, with the agent's own summary of it.
 */
export type Call = {
  kind: "tool" | "reasoning";
  key: string;
  /** The tool's name, as the agent called it. */
  name: string;
  verb: string;
  doing: string;
  icon: IconName;
  target: string;
  state: CallState;
  started: string;
  finished: string | null;
  error: string | null;
  input: Record<string, unknown>;
  output: string | null;
  summary: string | null;
};

/** What a message was given besides its text: a mark on the drawing, or a reference. */
export type Chip =
  | { kind: "mark"; number: number; color: MarkColor; shape: string }
  | { kind: "reference"; path: string; label: string };

/** What one part of a run shows as, in order. */
export type Block =
  | {
      kind: "message";
      key: string;
      sender: string;
      text: string;
      chips: Chip[];
      /** Whether it was sent to the agent while it worked. */
      steering: boolean;
      /** Why it did not reach the agent, when it did not. */
      failed: string | null;
    }
  | { kind: "said"; key: string; text: string }
  | {
      kind: "steps";
      key: string;
      calls: Call[];
      started: string;
      finished: string | null;
      state: "running" | "done" | "failed";
      /** Nothing has followed it yet in a run still working, so it stays open. */
      latest: boolean;
    }
  | {
      kind: "ended";
      key: string;
      status: Exclude<ImageRunStatus, "running">;
      /** None for a run whose process stopped without saying how. */
      ended: string | null;
      error: string | null;
      usage: ImageUsage | null;
    }
  | { kind: "result"; key: string; version: string };

/** One request on a drawing and everything that came of it. */
export type Run = {
  id: string;
  number: number;
  started: string;
  /** What its `started` event says: the request, the model, and whether it continued the session. */
  request: Record<string, unknown>;
  blocks: Block[];
  calls: Call[];
  live: boolean;
};

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

function firstLine(value: string): string {
  return value.trim().split("\n")[0]?.trim() ?? "";
}

/** Who sent a request or steering message, by the origin the activity records. */
function sender(origin: unknown): string {
  if (origin === APP) {
    return "You";
  }
  if (typeof origin === "string" && origin.startsWith("claude-code:")) {
    return "Claude Code";
  }
  return text(origin) ?? "Command line";
}

function markChips(marks: unknown): Chip[] {
  if (!Array.isArray(marks)) {
    return [];
  }
  return marks.map((mark: Record<string, unknown>, index) => ({
    kind: "mark",
    number: index + 1,
    color: MARK_COLORS.find((each) => each.id === mark.color)?.id ?? "red",
    shape: text(mark.shape) ?? "mark",
  }));
}

/** The references among `paths`, which the tool names `reference-1` and so on in the order they were given. */
function referenceChips(paths: string[]): Chip[] {
  return paths.flatMap((path) => {
    const found = REFERENCE.exec(path.replaceAll("\\", "/"));
    return found
      ? [{ kind: "reference" as const, path, label: `reference ${found[1]}` }]
      : [];
  });
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((each): each is string => typeof each === "string")
    : [];
}

function asked(run: RunFacts): Block {
  const folder = text(run.request.run_folder);
  const given =
    folder === null
      ? []
      : strings(run.request.images).map((image) => `${folder}/${image}`);
  return {
    kind: "message",
    key: `${run.id}:asked`,
    sender: sender(run.request.origin),
    text: run.prompt,
    chips: [...markChips(run.request.marks), ...referenceChips(given)],
    steering: false,
    failed: null,
  };
}

function steered(event: ImageEvent): Block {
  return {
    kind: "message",
    key: `${event.run_id}:steered:${event.time}`,
    sender: sender(event.data.origin),
    text: text(event.data.message) ?? "",
    chips: [
      ...markChips(event.data.marks),
      ...referenceChips(strings(event.data.references)),
    ],
    steering: true,
    failed: text(event.data.error),
  };
}

/** What a call works on, from what it was called with. */
function targetOf(name: string, input: Record<string, unknown>): string {
  if (name === "fileChange" && Array.isArray(input.changes)) {
    return input.changes
      .map((change: Record<string, unknown>) =>
        fileName(text(change.path) ?? ""),
      )
      .filter(Boolean)
      .join(", ");
  }
  for (const argument of TARGET_ARGUMENTS) {
    const value = text(input[argument]);
    if (value?.trim()) {
      return argument.includes("path") ? fileName(value) : firstLine(value);
    }
  }
  return "";
}

function wordsOf(
  name: string,
  target: string,
  command: string,
): { done: string; doing: string; icon: IconName } {
  if (TOOLS[name]?.icon === "terminal" && BUILD.test(command)) {
    return BUILT;
  }
  if ((name === "Read" && IMAGE.test(target)) || name === "imageView") {
    return LOOK;
  }
  return TOOLS[name] ?? { done: name, doing: name, icon: "terminal" };
}

function toolCall(runId: string, event: ImageEvent): Call {
  const data = (event.data.data ?? {}) as Record<string, unknown>;
  const name = text(data.tool_name) ?? "";
  const input =
    data.arguments && typeof data.arguments === "object"
      ? (data.arguments as Record<string, unknown>)
      : {};
  const target = targetOf(name, input);
  const words = wordsOf(name, target, text(input.command) ?? "");
  return {
    kind: "tool",
    key: `${runId}:${text(data.tool_call_id) ?? event.time}`,
    name,
    verb: words.done,
    doing: words.doing,
    icon: words.icon,
    target: words === BUILT ? "image.svg" : target,
    state: "running",
    started: event.time,
    finished: null,
    error: null,
    input,
    output: null,
    summary: null,
  };
}

/** The first line of a reasoning summary, without the Markdown that makes it a heading. */
function headline(summary: string): string {
  return firstLine(summary)
    .replace(/^#+\s*/, "")
    .replace(/\*\*|__/g, "")
    .trim();
}

function reasoning(runId: string, event: ImageEvent, summary: string): Call {
  return {
    kind: "reasoning",
    key: `${runId}:reasoning:${event.time}`,
    name: "",
    verb: "Reasoned",
    doing: "Reasoning",
    icon: "thought",
    target: headline(summary),
    state: "running",
    started: event.time,
    finished: null,
    error: null,
    input: {},
    output: null,
    summary,
  };
}

function latestOf(times: string[]): string | null {
  let latest: string | null = null;
  for (const time of times) {
    if (latest === null || Date.parse(time) > Date.parse(latest)) {
      latest = time;
    }
  }
  return latest;
}

/** One run's blocks: its request, what its agent said and did, how it ended, and what it made. */
function runOf(
  facts: RunFacts,
  number: number,
  live: boolean,
  /** How the run ended, when its events do not say. */
  ending: ImageRunStatus | null,
): Run {
  const run: Run = {
    id: facts.id,
    number,
    started: facts.started,
    request: facts.request,
    blocks: [asked(facts)],
    calls: [],
    live,
  };
  const byKey = new Map<string, Call>();
  const results: Block[] = [];
  // The reasoning nothing has followed yet, which whatever comes next ends.
  let thinking: Call | null = null;
  const stepsIn = (time: string): Extract<Block, { kind: "steps" }> => {
    const last = run.blocks.at(-1);
    if (last?.kind === "steps") {
      return last;
    }
    const block = {
      kind: "steps" as const,
      key: `${run.id}:${run.blocks.length}`,
      calls: [],
      started: time,
      finished: null,
      state: "done" as const,
      latest: false,
    };
    run.blocks.push(block);
    return block;
  };
  for (const event of facts.events.slice(1)) {
    if (thinking) {
      thinking.finished = event.time;
      thinking = null;
    }
    if (event.kind === "agent") {
      const kind = text(event.data.kind);
      const data = (event.data.data ?? {}) as Record<string, unknown>;
      const said = text(event.data.text) ?? "";
      if (kind === "tool_call") {
        const call = toolCall(run.id, event);
        byKey.set(call.key, call);
        stepsIn(event.time).calls.push(call);
      } else if (kind === "tool_result") {
        const call = byKey.get(`${run.id}:${text(data.tool_call_id) ?? ""}`);
        if (call) {
          call.finished = event.time;
          call.output = text(data.result);
          call.state = data.success === false ? "failed" : "done";
          call.error =
            data.success === false
              ? firstLine(call.output ?? "") || "It failed."
              : null;
        }
      } else if (kind === "reasoning" && said.trim()) {
        thinking = reasoning(run.id, event, said);
        stepsIn(event.time).calls.push(thinking);
      } else if (kind === "message" && said.trim()) {
        run.blocks.push({
          kind: "said",
          key: `${run.id}:said:${event.time}`,
          text: said,
        });
      }
    } else if (event.kind === "steered") {
      run.blocks.push(steered(event));
    } else if (event.kind === "version") {
      const id = text(event.data.id);
      if (id !== null) {
        results.push({ kind: "result", key: `${run.id}:${id}`, version: id });
      }
    } else if (event.kind === "finished" || event.kind === "failed") {
      const status = facts.status ?? "failed";
      run.blocks.push({
        kind: "ended",
        key: `${run.id}:ended`,
        status: status === "running" ? "failed" : status,
        ended: event.time,
        error: facts.error,
        usage: facts.usage,
      });
    }
  }
  // A run whose process ended before the run did says so only in its record.
  if (
    !live &&
    ending !== null &&
    ending !== "running" &&
    !run.blocks.some((block) => block.kind === "ended")
  ) {
    run.blocks.push({
      kind: "ended",
      key: `${run.id}:ended`,
      status: ending,
      ended: null,
      error: null,
      usage: null,
    });
  }
  run.blocks.push(...results);
  const lastBlock = run.blocks
    .filter((block) => block.kind !== "result")
    .at(-1);
  for (const block of run.blocks) {
    if (block.kind !== "steps") {
      continue;
    }
    for (const call of block.calls) {
      if (call.state === "running" && call.finished === null && !live) {
        call.state = "unfinished";
      } else if (call.state === "running" && call.finished !== null) {
        call.state = "done";
      }
    }
    run.calls.push(...block.calls);
    const states = block.calls.map((call) => call.state);
    block.state = states.includes("failed")
      ? "failed"
      : states.includes("running")
        ? "running"
        : "done";
    block.finished = latestOf(
      block.calls.map((call) => call.finished ?? call.started),
    );
    block.latest = live && lastBlock === block;
  }
  return run;
}

/** A drawing's runs, oldest first, from its activity. */
export function runsOf(drawing: ImageSummary, runs: Runs): Run[] {
  const last = drawing.last_run?.id ?? null;
  return [...runs.values()].map((facts, index) => {
    const isLast = facts.id === last;
    return runOf(
      facts,
      index + 1,
      isLast && drawing.status === "running",
      isLast ? drawing.status : null,
    );
  });
}

/** The call a working run is on now, and which of its calls that is, counting from 1. */
export function currentCall(
  run: Run | undefined,
): { call: Call; number: number } | null {
  if (!run) {
    return null;
  }
  for (let index = run.calls.length - 1; index >= 0; index -= 1) {
    if (run.calls[index].state === "running") {
      return { call: run.calls[index], number: index + 1 };
    }
  }
  return null;
}

const listeners = new Set<() => void>();
// The blocks of steps the person opened or closed, by the drawing and the block, kept for the session.
let opened: Record<string, boolean> = {};

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The blocks of steps the person opened or closed, which keep that until they change it again. */
export function useOpened(): Record<string, boolean> {
  return useSyncExternalStore(subscribe, () => opened);
}

export function toggleOpened(key: string, open: boolean) {
  opened = { ...opened, [key]: open };
  for (const listener of listeners) {
    listener();
  }
}
