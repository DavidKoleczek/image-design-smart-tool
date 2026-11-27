import { useState, useSyncExternalStore } from "react";

import type { IconName } from "@/components/ui/icon";
import type {
  ImageEvent,
  ImageRunStatus,
  ImageSummary,
  ImageUsage,
  SentMark,
} from "@/lib/api";
import { MARK_COLORS, type MarkColor } from "@/lib/marks";
import type { RunFacts, Runs } from "@/lib/runs";

const IMAGE = /\.(png|jpe?g|gif|webp)$/i;
// The command that builds a drawing, which reads better as what it makes than as the command.
const BUILD = /svg_image\.build/;
const REFERENCE = /(?:^|\/)reference-(\d+)\.\w+$/;
// The tool's own commands that send an image call, which show as the call and not as a line of shell.
const GENERATE = /image-design\s+generate-(?:openai|chatgpt)-image\b/;
// Asking one of them for its help sends no image call.
const HELP = /(?:^|\s)(?:--help|-h)(?=$|[\s"'|;&)])/;
const NAMED = /--name\s+("[^"]+"|\S+)/;
const APP = "app";
const DESIGN = "design";
// What a call through ChatGPT names as its image model, which ChatGPT picks.
const CHATGPT_MODEL = "chatgpt";

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
  Skill: { done: "Read the skill", doing: "Reading the skill", icon: "file" },
  fileChange: { done: "Edited", doing: "Editing", icon: "file-edit" },
  webSearch: { done: "Searched", doing: "Searching", icon: "search" },
};
const LOOK = { done: "Looked at", doing: "Looking at", icon: "image" as const };
const BUILT = { done: "Built", doing: "Building", icon: "terminal" as const };
const GENERATED = {
  done: "Generated",
  doing: "Generating",
  icon: "image" as const,
};
// The arguments that name what a call works on, in the order they are looked for.
const TARGET_ARGUMENTS = [
  "file_path",
  "path",
  "command",
  "pattern",
  "query",
  "url",
  "description",
  "skill",
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
  /** The image a step looked at, by its path on the machine the app runs on; null for any other step. */
  looked: string | null;
};

/** What a message was given besides its text: a mark on the drawing, or a reference. */
export type Chip =
  | { kind: "mark"; number: number; color: MarkColor; shape: string }
  | { kind: "reference"; path: string; label: string };

/** What an image in an image call is sent as. */
export type CallRole =
  "source" | "marked-copy" | "reference" | "marks" | "mask";

/** One request to an image model, as a card shows it: exactly what was sent, or would be, and how it went. */
export type ImageCall = {
  /** The id of the run that is the call. */
  id: string;
  /** The image it is for, which need not be the one whose conversation it shows in. */
  name: string;
  /** Whether the agent wrote it; a person otherwise, from the app or the command line. */
  agent: boolean;
  /** The id of the image whose agent wrote it, when an agent did. */
  parentImage: string | null;
  /** Who sent it, when the agent did not. */
  sender: string;
  method: "openai" | "chatgpt";
  model: string;
  /** Whether it changes an image that exists. */
  edits: boolean;
  prompt: string;
  /** In the order they are sent, by where each is kept. */
  images: { path: string; role: CallRole }[];
  /** What it set, by the name the method records each under. */
  parameters: [string, string][];
  state: "sending" | "sent" | "failed";
  /** Whether it failed because it was stopped. */
  stopped: boolean;
  started: string;
  finished: string | null;
  usage: ImageUsage | null;
  error: string | null;
  /** The versions it made, and for a draft the one it was kept as. */
  versions: string[];
  /** The in-progress image it sent last, by its index, while it is still sending. */
  preview: number | null;
  /** For a draft, which leaves the image as it is: the file it keeps its image in, and whether it has made it. */
  draft: { path: string; made: boolean } | null;
};

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
  | {
      kind: "result";
      key: string;
      version: string;
      /** The image the version is of, when it is not the one whose conversation this is. */
      name: string | null;
    }
  | { kind: "call"; key: string; call: ImageCall }
  | { kind: "note"; key: string; text: string };

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
  /** In an image's conversation: a turn of the agent, or an image call nobody's agent made. */
  kind?: "agent" | "call";
  /** Whether the agent started a conversation over, having had one on the image before. */
  fresh?: boolean;
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

/** Whether a command sends an image call with one of the tool's own commands. */
function generates(command: string): boolean {
  const found = GENERATE.exec(command);
  return (
    found !== null && !HELP.test(command.slice(found.index + found[0].length))
  );
}

function wordsOf(
  name: string,
  target: string,
  command: string,
): { done: string; doing: string; icon: IconName } {
  if (TOOLS[name]?.icon === "terminal" && BUILD.test(command)) {
    return BUILT;
  }
  if (TOOLS[name]?.icon === "terminal" && generates(command)) {
    return GENERATED;
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
    target:
      words === BUILT
        ? "image.svg"
        : words === GENERATED
          ? (NAMED.exec(text(input.command) ?? "")?.[1] ?? "").replaceAll(
              '"',
              "",
            )
          : target,
    state: "running",
    started: event.time,
    finished: null,
    error: null,
    input,
    output: null,
    summary: null,
    looked:
      words === LOOK
        ? (text(input.file_path) ?? text(input.path) ?? null)
        : null,
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
    looked: null,
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
  /** What came of the run besides its own events, such as the image calls its agent made, each placed by its time. */
  children: { time: string; blocks: Block[] }[] = [],
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
  const childTimes = children.map((child) => Date.parse(child.time));
  const every: Call[] = [];
  const waiting = [...children].sort(
    (a, b) => Date.parse(a.time) - Date.parse(b.time),
  );
  const placeUntil = (time: string | null) => {
    while (
      waiting.length > 0 &&
      (time === null || Date.parse(waiting[0].time) <= Date.parse(time))
    ) {
      run.blocks.push(...(waiting.shift()?.blocks ?? []));
    }
  };
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
    // A run's ending comes after everything it started.
    placeUntil(
      event.kind === "finished" || event.kind === "failed" ? null : event.time,
    );
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
        every.push(call);
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
        every.push(thinking);
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
        results.push({
          kind: "result",
          key: `${run.id}:${id}`,
          version: id,
          name: null,
        });
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
  placeUntil(null);
  run.blocks.push(...results);
  // A step that sent an image call shows as the call's card, which a child of the run started while it ran is. One
  // that started none, as one refused before it was sent, stays a step.
  const sent = (call: Call) =>
    call.verb === GENERATED.done &&
    childTimes.some(
      (time) =>
        time >= Date.parse(call.started) &&
        (call.finished === null || time <= Date.parse(call.finished)),
    );
  for (const block of run.blocks) {
    if (block.kind === "steps") {
      block.calls = block.calls.filter((call) => !sent(call));
    }
  }
  run.blocks = run.blocks.filter(
    (block) => block.kind !== "steps" || block.calls.length > 0,
  );
  const lastBlock = run.blocks
    .filter((block) => block.kind !== "result")
    .at(-1);
  for (const call of every) {
    if (call.state === "running" && call.finished === null && !live) {
      call.state = "unfinished";
    } else if (call.state === "running" && call.finished !== null) {
      call.state = "done";
    }
  }
  run.calls.push(...every);
  for (const block of run.blocks) {
    if (block.kind !== "steps") {
      continue;
    }
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

const ROLES: [RegExp, CallRole][] = [
  [/(?:^|\/)image\.\w+$/, "source"],
  [/(?:^|\/)marked\.\w+$/, "marked-copy"],
  [/(?:^|\/)marks\.\w+$/, "marks"],
  [/(?:^|\/)mask\.\w+$/, "mask"],
];
// What a call set that a card shows, in the order it shows them.
const PARAMETERS = [
  "quality",
  "complexity",
  "size",
  "background",
  "frames",
  "frame_ms",
  "compression",
  "transparent",
  "reasoning_effort",
];

function shownValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    return value.join("x");
  }
  return typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
    ? String(value)
    : null;
}

function isDesign(facts: RunFacts): boolean {
  return facts.request.method === DESIGN;
}

/** The versions a run made, by their ids, in the order it made them, and for a draft on `image` the one it was kept as. */
function versionsOf(facts: RunFacts, image: ImageSummary): string[] {
  const made = facts.events.flatMap((event) => {
    const id = event.kind === "version" ? text(event.data.id) : null;
    return id === null ? [] : [id];
  });
  // A draft is kept after its run has ended, so the version, which names the draft's run, tells it.
  const kept =
    text(facts.request.draft) !== null &&
    (text(facts.request.name) ?? image.name) === image.name
      ? image.versions
          .filter((version) => version.run_id === facts.id)
          .map((version) => version.id)
      : [];
  return [...made, ...kept];
}

/** A run as the image call it is. */
function callOf(
  facts: RunFacts,
  image: ImageSummary,
  /** Whether its process is still at it. */
  live: boolean,
): ImageCall {
  const request = facts.request;
  const folder = text(request.run_folder);
  const located = (path: string) =>
    folder === null ? path : `${folder}/${path}`;
  const images: ImageCall["images"] = strings(request.images).map((path) => ({
    path: located(path),
    role: ROLES.find(([pattern]) => pattern.test(path))?.[1] ?? "reference",
  }));
  for (const [field, role] of [
    ["markup", "marks"],
    ["mask", "mask"],
  ] as const) {
    const path = text(request[field]);
    if (path !== null) {
      images.push({ path: located(path), role });
    }
  }
  const chatgpt = typeof request.codex_model === "string";
  const draft = text(request.draft);
  const status = facts.status as string | null;
  const state =
    status === "done" ? "sent" : status === null && live ? "sending" : "failed";
  return {
    id: facts.id,
    name: text(request.name) ?? image.name,
    agent: text(request.parent) !== null,
    parentImage: text(request.parent_image),
    sender: sender(request.origin),
    method: chatgpt ? "chatgpt" : "openai",
    model: chatgpt ? CHATGPT_MODEL : (text(request.model) ?? ""),
    edits: images.some((each) => each.role === "source"),
    prompt: facts.prompt,
    images,
    parameters: PARAMETERS.flatMap((name) => {
      const value = shownValue(request[name]);
      return value === null || value === "auto" || value === "false"
        ? []
        : [[name, value] as [string, string]];
    }),
    state,
    stopped: state === "failed" && status === "cancelled",
    started: facts.started,
    finished: facts.finished,
    usage: facts.usage,
    error:
      state !== "failed"
        ? null
        : (facts.error ??
          (status === "cancelled"
            ? "It was stopped."
            : status === "timed-out"
              ? "It ran out of time."
              : "It stopped before it finished.")),
    versions: versionsOf(facts, image),
    preview: state === "sending" ? (facts.previews.at(-1) ?? null) : null,
    draft:
      draft === null
        ? null
        : {
            path: draft,
            made: facts.events.some((event) => event.kind === "draft"),
          },
  };
}

/** A call's card, then each version it made, of this image or of the other one it was for. */
function callBlocks(call: ImageCall, image: ImageSummary): Block[] {
  return [
    { kind: "call", key: `${call.id}:call`, call },
    ...call.versions.map((version) => ({
      kind: "result" as const,
      key: `${call.id}:${version}`,
      version,
      name: call.name === image.name ? null : call.name,
    })),
  ];
}

/**
 * An image's conversation, oldest first, from its activity: each turn of the agent with the image calls it made
 * where it made them, and each image call nobody's agent made as a turn of its own.
 */
export function conversationOf(image: ImageSummary, runs: Runs): Run[] {
  const all = [...runs.values()];
  const liveDesign =
    image.design?.status === "running" ? image.design.run_id : null;
  const lastRun = image.status === "running" ? image.last_run?.id : null;
  const design = all.filter(isDesign);
  const calls = all.filter((facts) => !isDesign(facts));
  const conversation: Run[] = [];
  for (const facts of design) {
    const live = facts.id === liveDesign;
    const children = calls
      .filter((call) => text(call.request.parent) === facts.id)
      .map((call) => ({
        time: call.started,
        blocks: callBlocks(
          callOf(
            call,
            image,
            call.id === lastRun || (live && call.finished === null),
          ),
          image,
        ),
      }));
    const run = runOf(
      facts,
      0,
      live,
      facts.id === image.design?.run_id ? image.design.status : null,
      children,
    );
    run.kind = "agent";
    run.fresh =
      !facts.request.resumed &&
      design.some(
        (other) => Date.parse(other.started) < Date.parse(facts.started),
      );
    const since = strings(facts.request.since).length;
    if (since > 0) {
      run.blocks.splice(1, 0, {
        kind: "note",
        key: `${facts.id}:since`,
        text:
          since === 1
            ? "Told of 1 call made since its last turn."
            : `Told of ${since} calls made since its last turn.`,
      });
    }
    conversation.push(run);
  }
  const ours = new Set(design.map((facts) => facts.id));
  for (const facts of calls) {
    const parent = text(facts.request.parent);
    if (parent !== null && ours.has(parent)) {
      continue;
    }
    const call = callOf(facts, image, facts.id === lastRun);
    conversation.push({
      id: facts.id,
      number: 0,
      started: facts.started,
      request: facts.request,
      blocks: callBlocks(call, image),
      calls: [],
      live: call.state === "sending",
      kind: "call",
    });
  }
  conversation.sort((a, b) => Date.parse(a.started) - Date.parse(b.started));
  conversation.forEach((run, index) => {
    run.number = index + 1;
  });
  return conversation;
}

/**
 * The turn a message the person sends starts, as the thread shows it before the run is going: the message, and the
 * agent it goes to. An image's agent's turn is `kind` agent.
 */
export function sentTurn(
  conversation: Run[],
  message: string,
  marks: SentMark[],
  request: { model: string; reasoning_effort: string; resumed: boolean },
  kind?: "agent",
): Run {
  const started = new Date().toISOString();
  const id = `sent:${started}`;
  return {
    id,
    number: conversation.length + 1,
    started,
    request,
    blocks: [
      {
        kind: "message",
        key: `${id}:asked`,
        sender: sender(APP),
        text: message,
        chips: markChips(marks),
        steering: false,
        failed: null,
      },
    ],
    calls: [],
    live: true,
    kind,
    fresh:
      kind === "agent" &&
      !request.resumed &&
      conversation.some((run) => run.kind === "agent"),
  };
}

/**
 * The thread as it shows under `key`: `conversation`, and after it the turn a message just sent starts, until the run
 * it starts is among the conversation. Starting a run takes a moment, and the message shows meanwhile.
 */
export function useSentTurn(key: string, conversation: Run[]) {
  const [sent, setSent] = useState<{
    key: string;
    turn: Run;
    runId: string | null;
  } | null>(null);
  // The run is kept a moment before the request that starts it answers with its id, and may be listed by then.
  const shown =
    sent !== null &&
    sent.key === key &&
    !conversation.some(
      (run) =>
        run.id === sent.runId ||
        Date.parse(run.started) >= Date.parse(sent.turn.started),
    );
  return {
    runs: shown ? [...conversation, sent.turn] : conversation,
    /** The message was sent, and starts `turn`. */
    send: (turn: Run) => setSent({ key, turn, runId: null }),
    /** The run it started is `runId`, which shows in its place once listed. */
    started: (runId: string) =>
      setSent((before) => before && { ...before, runId }),
    /** It did not start a run. */
    failed: () => setSent(null),
  };
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

/** Forget the blocks opened or closed, for a workspace shown next, whose images are others under the same names. */
export function forgetOpened() {
  opened = {};
  for (const listener of listeners) {
    listener();
  }
}
