import { useSyncExternalStore } from "react";

import type {
  AppDesignRequest,
  AppSvgRequest,
  DesignImageMethod,
  DrawRequest,
  ImageMethods,
  ImageSummary,
  IntelligenceModel,
  SentMark,
  SentReference,
  SvgImageMethod,
} from "@/lib/api";
import { movedPath } from "@/lib/paths";
import { onRenamed, rekey } from "@/lib/renames";
import {
  DRAWING,
  sourceReference,
  type Source,
  type Target,
} from "@/lib/request";

/** `AppSvgRequest()` in schemas.py, for when the state cannot be read. */
export const DEFAULT_SVG: AppSvgRequest = {
  agent_provider: null,
  model: null,
  reasoning_effort: null,
  canvas: null,
  max_bytes: null,
  timeout_seconds: null,
};

/** `AppDesignRequest()` in schemas.py, for when the state cannot be read. */
export const DEFAULT_DESIGN: AppDesignRequest = {
  agent_provider: null,
  model: null,
  reasoning_effort: null,
  image_model: null,
  size: null,
  quality: null,
};

/** The canvases offered for a new drawing. A drawing keeps its canvas, which a message can ask to change. */
export const CANVASES: { label: string; size: [number, number] }[] = [
  { label: "Square", size: [512, 512] },
  { label: "Landscape", size: [768, 512] },
  { label: "Portrait", size: [512, 768] },
  { label: "Icon", size: [24, 24] },
];

const PROVIDERS: Record<string, string> = { codex: "Codex", claude: "Claude" };
const EFFORTS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "Extra high",
  max: "Max",
  ultra: "Ultra",
};

export function providerLabel(provider: string): string {
  return PROVIDERS[provider] ?? provider;
}

export function effortLabel(effort: string): string {
  return EFFORTS[effort] ?? effort;
}

/** What a drawing is held to: its canvas, and the most bytes its file may have, null for no limit. */
export type Budgets = { canvas: [number, number]; max_bytes: number | null };

/** An agent that works on an image: the model picked last when it is still offered, else the default. */
export type Agent = {
  provider: string;
  model: string;
  effort: string;
  /** The model's own entry; null when no agent provider is installed. */
  entry: IntelligenceModel | null;
};

export function agentOf(
  options: AppSvgRequest | AppDesignRequest,
  offered: SvgImageMethod | DesignImageMethod,
): Agent {
  const { models, default: fallback } = offered;
  const entry =
    models.find(
      (model) =>
        model.id === options.model &&
        (options.agent_provider === null ||
          model.agent_provider === options.agent_provider),
    ) ??
    models.find((model) => model.id === fallback.model) ??
    models[0] ??
    null;
  const efforts = entry?.reasoning_efforts ?? [];
  const effort =
    options.reasoning_effort !== null &&
    efforts.includes(options.reasoning_effort)
      ? options.reasoning_effort
      : efforts.includes(fallback.reasoning_effort) || efforts.length === 0
        ? fallback.reasoning_effort
        : efforts[0];
  return {
    provider: entry?.agent_provider ?? fallback.agent_provider,
    model: entry?.id ?? fallback.model,
    effort,
    entry,
  };
}

function pair(value: unknown): [number, number] | null {
  return Array.isArray(value) &&
    typeof value[0] === "number" &&
    typeof value[1] === "number"
    ? [value[0], value[1]]
    : null;
}

function limit(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/** The size in pixels of what shows of an image, which a drawing made from it matches unless told otherwise. */
export function sizeOf(source: Source): [number, number] | null {
  const { width, height } = source.shown;
  return width !== null && height !== null ? [width, height] : null;
}

/**
 * The budgets a request on `drawing` starts from: those its last run went by, or for an SVG the tool never drew, its
 * own size and no limit. A new drawing takes those picked last, and one made from an image in view, that image's size.
 */
export function budgetsOf(
  drawing: ImageSummary | null,
  from: Source | null,
  options: AppSvgRequest,
  methods: ImageMethods,
): Budgets {
  if (drawing === null) {
    return {
      canvas:
        (from && sizeOf(from)) ?? options.canvas ?? methods.svg.default_canvas,
      max_bytes: options.max_bytes,
    };
  }
  const request =
    drawing.last_run?.method === "svg" ? drawing.last_run.request : {};
  const own: [number, number] | null =
    drawing.width !== null && drawing.height !== null
      ? [drawing.width, drawing.height]
      : null;
  return {
    canvas: pair(request.canvas) ?? own ?? methods.svg.default_canvas,
    max_bytes: limit(request.max_bytes),
  };
}

/** Whether a request on the drawing continues its agent's last conversation, with the agent provider it ran on. */
export function conversationOf(drawing: ImageSummary | null): {
  provider: string;
} | null {
  const run = drawing?.last_run;
  return run && run.method === "svg" && run.session_id && run.agent_provider
    ? { provider: run.agent_provider }
    : null;
}

/** The request to draw, as the tool takes it. */
export function drawOf(
  target: Target,
  message: string,
  agent: Agent,
  options: AppSvgRequest,
  budgets: Budgets,
  /** The budgets changed for this drawing, the only ones an edit sends: the rest keep the drawing's. */
  changed: Partial<Budgets>,
  resume: boolean,
  references: SentReference[],
  marks: SentMark[],
): DrawRequest {
  const sent = target.from
    ? [sourceReference(target.from), ...references]
    : references;
  const { canvas, ...rest }: Partial<Budgets> = target.image
    ? changed
    : budgets;
  return {
    prompt: message,
    name: target.image ? target.image.name : `${target.name}${DRAWING}`,
    ...(sent.length > 0 ? { references: sent } : {}),
    ...(marks.length > 0 ? { marks } : {}),
    ...(canvas && !target.image ? { canvas } : {}),
    ...rest,
    resume_session: resume,
    agent_provider: agent.provider,
    model: agent.model,
    reasoning_effort: agent.effort,
    timeout_seconds: options.timeout_seconds,
  };
}

/** What is picked for one drawing for the session: budgets changed from the drawing's. */
export type Drawing = {
  budgets: Partial<Budgets>;
};

const NOTHING: Drawing = { budgets: {} };
const listeners = new Set<() => void>();
const drawings = new Map<string, Drawing>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function set(name: string, drawing: Drawing) {
  drawings.set(name, drawing);
  for (const listener of listeners) {
    listener();
  }
}

export function useDrawing(name: string): Drawing {
  return useSyncExternalStore(subscribe, () => drawings.get(name) ?? NOTHING);
}

export function changeDrawing(name: string, change: Partial<Drawing>) {
  set(name, { ...(drawings.get(name) ?? NOTHING), ...change });
}

/** Once a request has gone, the budgets it set are the drawing's. */
export function sentDrawing(name: string) {
  set(name, NOTHING);
}

/** Forget what was picked for a drawing, as once it is no longer being worked on. */
export function dropDrawing(name: string) {
  if (drawings.delete(name)) {
    for (const listener of listeners) {
      listener();
    }
  }
}

onRenamed((from, to) => {
  if (rekey(drawings, (name) => movedPath(name, from, to))) {
    for (const listener of listeners) {
      listener();
    }
  }
});
