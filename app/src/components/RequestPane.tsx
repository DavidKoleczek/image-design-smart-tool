import { useEffect, useState, type ReactNode } from "react";

import { RequestPreview } from "@/components/RequestPreview";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Section } from "@/components/ui/section";
import { Segmented } from "@/components/ui/segmented";
import { Select } from "@/components/ui/select";
import { Thumb } from "@/components/ui/thumb";
import { Tooltip } from "@/components/ui/tooltip";
import { ValueField } from "@/components/ui/value-field";
import {
  cancelImage,
  generateImage,
  type AppImageRequest,
  type AppMethod,
  type ImageListing,
  type ImageMethods,
  type ImageSummary,
} from "@/lib/api";
import { moveDraft, NEW_IMAGE, updateDraft, useDraft } from "@/lib/drafts";
import { describe, describeEnding } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { useMethods } from "@/lib/methods";
import {
  CHATGPT,
  CHATGPT_LABEL,
  freeName,
  problemOf,
  requestOf,
  resolve,
  SIZES,
  stillFormats,
  typedName,
  type Resolved,
  type Target,
} from "@/lib/request";
import type { Runs } from "@/lib/runs";
import { updateAppState, useAppState } from "@/lib/state";
import { ago, useElapsed } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { Shown } from "@/lib/viewed";

const BY_CHATGPT = "Chosen by ChatGPT";
const ONLY_CHATGPT = "Only with ChatGPT";
const KEEPS_FORMAT = "An edit keeps the image's format";
const NO_TRANSPARENCY = "JPEG has no transparency";
const AUTO = "auto";

const QUALITIES: Record<string, string> = { xhigh: "Extra high" };
const FORMATS: Record<string, string> = {
  ".png": "PNG",
  ".jpg": "JPEG",
  ".webp": "WebP",
};
// The order the backgrounds read in: the service's choice, then the two it can be told.
const BACKGROUNDS = [AUTO, "opaque", "transparent"];

function titled(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

// The runs seen working since the app opened. How one of them ended is said once it has; one that ended before the
// app opened is old news, which the image's status already tells.
const watched = new Set<string>();

function update(change: Partial<AppImageRequest>) {
  updateAppState((current) => ({
    ...current,
    request: { ...current.request, ...change },
  }));
}

/** A control of the form beside its label. `off` says why it does not apply now, and greys the label. */
function Row({
  label,
  off,
  children,
}: {
  label: string;
  off?: string;
  children: ReactNode;
}) {
  return (
    <div title={off} className="flex min-h-7 items-center gap-2">
      <span
        className={cn(
          "w-21 shrink-0 text-label",
          off ? "text-ink-faint" : "text-ink-muted",
        )}
      >
        {label}
      </span>
      <div className="flex min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** What the request is for, the image in view or a new image and its name, and the model it goes to. */
function TargetBlock({
  target,
  typed,
  resolved,
  methods,
}: {
  target: Target;
  /** A new image's name as it stands in the field. */
  typed: string;
  resolved: Resolved;
  methods: ImageMethods;
}) {
  const { openai, chatgpt } = methods;
  const shown = target.image ? target.shown : null;
  return (
    <div className="flex flex-col gap-2 border-b border-line p-3">
      <div className="flex items-center gap-2.5">
        {target.image && shown ? (
          <>
            <Thumb
              picture={shown.picture && { ...shown.picture, small: true }}
              shape={shown}
              className="size-11"
            />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="truncate mono-value">{target.image.name}</span>
              <span className="flex gap-2 mono-annotation text-ink-muted">
                {shown.version && <span>{shown.version.id}</span>}
                {shown.width !== null && shown.height !== null && (
                  <span>{dimensions(shown.width, shown.height)}</span>
                )}
              </span>
            </div>
          </>
        ) : (
          <>
            <span className="grid size-11 shrink-0 place-items-center rounded-sm border border-dashed border-line-control text-ink-muted">
              <Icon name="add" size={20} />
            </span>
            <label className="flex h-7 min-w-0 flex-1 items-center gap-0.5 rounded-sm border border-line-control bg-field px-2 focus-within:border-ink focus-within:bg-panel focus-within:focus-ring">
              <input
                aria-label="Name"
                spellCheck={false}
                autoComplete="off"
                value={typed}
                onChange={(event) =>
                  updateDraft(NEW_IMAGE, { name: event.target.value })
                }
                className="min-w-0 flex-1 bg-transparent mono-value text-ink outline-none"
              />
              <span className="mono-value text-ink-muted">
                {resolved.format}
              </span>
            </label>
          </>
        )}
      </div>
      <Row label="Model">
        <Select
          label="Image model"
          value={resolved.model}
          onChange={(model) => update({ model })}
          items={[
            ...openai.models.map((model) => ({
              value: model.id,
              label: model.label,
              group: "OpenAI API",
              disabled: openai.ready
                ? undefined
                : (openai.problem ?? "Not set up"),
            })),
            {
              value: CHATGPT,
              label: CHATGPT_LABEL,
              group: "ChatGPT",
              disabled: chatgpt.ready
                ? undefined
                : (chatgpt.problem ?? "Not set up"),
            },
          ]}
        />
      </Row>
    </div>
  );
}

type EarlierPrompt = { key: string; tag: string; when: string; text: string };

/** The prompts a request can start from: those of the image's versions, newest first, or each image's last. */
function earlierPrompts(
  target: Target,
  runs: Runs,
  listing: ImageListing | null,
): EarlierPrompt[] {
  const prompts: EarlierPrompt[] = [];
  const seen = new Set<string>();
  const add = (prompt: EarlierPrompt) => {
    if (prompt.text.trim() && !seen.has(prompt.text)) {
      seen.add(prompt.text);
      prompts.push(prompt);
    }
  };
  if (target.image) {
    for (const version of [...target.image.versions].reverse()) {
      const run = version.run_id !== null ? runs.get(version.run_id) : null;
      if (run) {
        add({
          key: version.id,
          tag: version.id,
          when: version.created,
          text: run.prompt,
        });
      }
    }
  } else {
    for (const image of listing?.images ?? []) {
      if (image.last_run) {
        add({
          key: image.name,
          tag: image.name,
          when: image.last_run.started,
          text: image.last_run.prompt,
        });
      }
    }
  }
  return prompts;
}

/** Fills the prompt from an earlier one, in place of what is written. */
function PromptPicker({
  target,
  prompts,
  current,
  onPick,
}: {
  target: Target;
  prompts: EarlierPrompt[];
  current: string;
  onPick: (prompt: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            size="sm"
            disabled={prompts.length === 0}
            title={prompts.length === 0 ? "No earlier prompts yet" : undefined}
          />
        }
      >
        <Icon name="clock" />
        {target.image ? "Load from version" : "Load from image"}
      </PopoverTrigger>
      <PopoverContent
        label="Earlier prompts"
        className="flex max-h-[min(420px,70vh)] w-89 flex-col overflow-y-auto"
      >
        {prompts.map((prompt) => (
          <button
            key={prompt.key}
            type="button"
            onClick={() => {
              onPick(prompt.text);
              setOpen(false);
            }}
            className={cn(
              "flex shrink-0 cursor-default flex-col gap-1 rounded-sm px-2 py-1.5 text-left outline-none hover:bg-hover focus-visible:bg-hover",
              prompt.text === current && "bg-accent-soft",
            )}
          >
            <span className="flex min-w-0 items-center gap-2 mono-annotation">
              <span className="truncate text-ink">{prompt.tag}</span>
              <span className="shrink-0 text-ink-muted">
                {ago(prompt.when)}
              </span>
            </span>
            <span className="line-clamp-2 text-label font-normal">
              {prompt.text}
            </span>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

/** What the image comes out as. An option the picked model or the image's format does not take is greyed out. */
function Output({
  options,
  resolved,
  methods,
  target,
}: {
  options: AppImageRequest;
  resolved: Resolved;
  methods: ImageMethods;
  target: Target;
}) {
  const [advanced, setAdvanced] = useState(false);
  const { openai, chatgpt } = methods;
  const byChatGPT = resolved.method === "chatgpt" ? BY_CHATGPT : undefined;
  const onlyChatGPT = resolved.method === "chatgpt" ? undefined : ONLY_CHATGPT;
  const source = target.image ? target.shown : null;
  const size = resolved.size ? resolved.size.join("x") : AUTO;
  const codexModel = chatgpt.models.find(
    (model) => model.id === resolved.codexModel,
  );
  return (
    <div className="flex flex-col gap-2">
      <Row label="Size" off={byChatGPT}>
        <Select
          label="Size"
          value={size}
          disabled={byChatGPT !== undefined}
          onChange={(picked) => {
            const size =
              SIZES.find((each) => each.size.join("x") === picked)?.size ??
              null;
            if (target.image) {
              updateDraft(target.image.name, { size });
            } else {
              update({ size });
            }
          }}
          items={[
            {
              value: AUTO,
              label: target.image ? "Match source" : "Auto",
              aside:
                source && source.width !== null && source.height !== null
                  ? dimensions(source.width, source.height)
                  : undefined,
            },
            ...SIZES.map((each) => ({
              value: each.size.join("x"),
              label: each.label,
              aside: dimensions(...each.size),
            })),
          ]}
        />
      </Row>
      <Row label="Quality" off={byChatGPT}>
        <Select
          label="Quality"
          value={options.quality}
          disabled={byChatGPT !== undefined}
          onChange={(quality) => update({ quality })}
          items={openai.qualities.map((quality) => ({
            value: quality,
            label: QUALITIES[quality] ?? titled(quality),
          }))}
        />
      </Row>
      <Row label="Format">
        <Segmented
          label="Format"
          size="sm"
          full
          className="flex-1"
          value={resolved.format in FORMATS ? resolved.format : null}
          onChange={(format) => update({ format })}
          options={stillFormats(methods).map((format) => ({
            value: format,
            label: FORMATS[format] ?? format.slice(1).toUpperCase(),
            disabled: target.image
              ? KEEPS_FORMAT
              : (byChatGPT ??
                (format === ".jpg" && options.background === "transparent"
                  ? NO_TRANSPARENCY
                  : undefined)),
          }))}
        />
      </Row>
      <Row label="Background">
        <Segmented
          label="Background"
          size="sm"
          full
          className="flex-1"
          value={
            byChatGPT && resolved.background !== "transparent"
              ? AUTO
              : resolved.background
          }
          onChange={(background) =>
            update({
              background,
              // A new image asked to be transparent moves to a format that can be.
              ...(background === "transparent" &&
              !target.image &&
              options.format === ".jpg"
                ? { format: ".png" }
                : {}),
            })
          }
          options={BACKGROUNDS.filter((background) =>
            openai.backgrounds.includes(background),
          ).map((background) => ({
            value: background,
            label: titled(background),
            disabled:
              background === "opaque"
                ? byChatGPT
                : background === "transparent" &&
                    target.image &&
                    !resolved.transparency
                  ? NO_TRANSPARENCY
                  : undefined,
          }))}
        />
      </Row>
      <Row label="Images" off={byChatGPT}>
        <ValueField
          label="Count"
          className="flex-1"
          value={resolved.count}
          min={1}
          max={openai.max_count}
          disabled={byChatGPT !== undefined}
          onChange={(count) => update({ count })}
        />
      </Row>
      <button
        type="button"
        aria-expanded={advanced}
        onClick={() => setAdvanced((open) => !open)}
        className="-ml-1 flex h-6 cursor-default items-center gap-1 self-start rounded-sm pr-1.5 pl-0.5 text-label text-ink-muted hover:bg-hover hover:text-ink focus-visible:focus-ring focus-visible:outline-none"
      >
        <Icon
          name="chevron"
          className={cn("transition-transform", !advanced && "-rotate-90")}
        />
        Advanced
      </button>
      {advanced && (
        <>
          <Row label="Complexity" off={byChatGPT}>
            <Segmented
              label="Complexity"
              size="sm"
              full
              className="flex-1"
              value={options.complexity ?? AUTO}
              onChange={(complexity) =>
                update({ complexity: complexity === AUTO ? null : complexity })
              }
              options={[AUTO, ...openai.complexities].map((complexity) => ({
                value: complexity,
                label: titled(complexity),
                disabled: byChatGPT,
              }))}
            />
          </Row>
          <Row
            label="Compression"
            off={
              byChatGPT ??
              (resolved.compression === null ? "For a JPEG or WebP" : undefined)
            }
          >
            <ValueField
              label="Level"
              className="flex-1"
              value={options.compression}
              min={0}
              max={100}
              unit="%"
              disabled={
                resolved.compression === null || byChatGPT !== undefined
              }
              onChange={(compression) => update({ compression })}
            />
          </Row>
          <Row label="Codex model" off={onlyChatGPT}>
            <Select
              label="Codex model"
              value={resolved.codexModel}
              disabled={onlyChatGPT !== undefined}
              onChange={(codex_model) => update({ codex_model })}
              items={chatgpt.models.map((model) => ({
                value: model.id,
                label: model.label,
              }))}
            />
          </Row>
          <Row label="Reasoning" off={onlyChatGPT}>
            <Select
              label="Reasoning effort"
              value={resolved.reasoningEffort}
              disabled={onlyChatGPT !== undefined}
              onChange={(reasoning_effort) => update({ reasoning_effort })}
              items={(
                codexModel?.reasoning_efforts ?? [resolved.reasoningEffort]
              ).map((effort) => ({
                value: effort,
                label: QUALITIES[effort] ?? titled(effort),
              }))}
            />
          </Row>
        </>
      )}
    </div>
  );
}

function Elapsed({ since }: { since: string }) {
  return (
    <span className="mono-annotation text-ink-muted">{useElapsed(since)}</span>
  );
}

/** The request to an image model: what it is for, the prompt, what comes out, and Generate, or Stop while it works. */
function RequestForm({
  methods,
  listing,
  image,
  shown,
  runs,
  onCreated,
  onChanged,
  onView,
}: {
  methods: ImageMethods;
  listing: ImageListing | null;
  image: ImageSummary | null;
  shown: Shown | null;
  runs: Runs;
  onCreated: (name: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onView: (version: string | null) => void;
}) {
  const { state } = useAppState();
  const options = state.request;
  const draft = useDraft(image ? image.name : NEW_IMAGE);
  const [open, setOpen] = useState({ prompt: true, output: true });
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const resolved = resolve(options, methods, image, draft.size);
  const typed = draft.name ?? freeName(listing, resolved.format);
  const target: Target =
    image && shown
      ? { image, shown }
      : { image: null, name: typedName(typed, stillFormats(methods)) };
  const problem = problemOf(target, draft.prompt, resolved, methods, listing);
  const run = image?.last_run ?? null;
  const running = image?.status === "running" && run !== null;
  const prompts = earlierPrompts(target, runs, listing);

  useEffect(() => {
    for (const each of listing?.images ?? []) {
      if (each.status === "running" && each.last_run) {
        watched.add(each.last_run.id);
      }
    }
  }, [listing]);

  const setPrompt = (prompt: string) =>
    updateDraft(image ? image.name : NEW_IMAGE, { prompt });

  const generate = async () => {
    if (problem !== null || starting || running) {
      return;
    }
    setStarting(true);
    setFailure(null);
    try {
      const started = await generateImage(
        requestOf(target, draft.prompt, options, resolved, methods),
      );
      watched.add(started.run_id);
      if (target.image) {
        // What the run makes lands in the image's file, so that is what shows while it works.
        onView(null);
        await onChanged();
      } else {
        moveDraft(NEW_IMAGE, started.name);
        await onCreated(started.name);
      }
    } catch (cause) {
      setFailure(`The request did not start. ${describe(cause)}`);
    } finally {
      setStarting(false);
    }
  };

  const stop = async () => {
    if (!image || !run) {
      return;
    }
    setStopping(run.id);
    setFailure(null);
    try {
      await cancelImage(image.name);
    } catch (cause) {
      setStopping(null);
      setFailure(`Could not stop the request. ${describe(cause)}`);
    }
  };

  const ended =
    image && run && !running && watched.has(run.id) && dismissed !== run.id
      ? image.status
      : null;

  return (
    <div
      className="flex min-h-0 flex-1 flex-col"
      onKeyDown={(event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
          event.preventDefault();
          void generate();
        }
      }}
    >
      <div className="min-h-0 flex-1 overflow-y-auto">
        <TargetBlock
          target={target}
          typed={typed}
          resolved={resolved}
          methods={methods}
        />
        <Section
          title="Prompt"
          open={open.prompt}
          onOpenChange={(prompt) => setOpen({ ...open, prompt })}
          aside={
            <PromptPicker
              target={target}
              prompts={prompts}
              current={draft.prompt}
              onPick={setPrompt}
            />
          }
        >
          <Textarea
            aria-label="Prompt"
            value={draft.prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={
              image
                ? "Describe the change, like make the vase purple"
                : "Describe the image: subject, composition, style, and anything it must not have"
            }
            className="block field-sizing-content max-h-80 min-h-19 resize-none"
          />
        </Section>
        <Section
          title="Output"
          open={open.output}
          onOpenChange={(output) => setOpen({ ...open, output })}
        >
          <Output
            options={options}
            resolved={resolved}
            methods={methods}
            target={target}
          />
        </Section>
      </div>
      <footer className="shrink-0 border-t border-line bg-panel">
        {(failure ||
          ended === "failed" ||
          ended === "timed-out" ||
          ended === "cancelled" ||
          (problem && !problem.quiet && !running)) && (
          <div className="flex flex-col gap-2 px-3 pt-2.5">
            {failure && (
              <Notice onDismiss={() => setFailure(null)}>{failure}</Notice>
            )}
            {run &&
              (ended === "failed" ||
                ended === "timed-out" ||
                ended === "cancelled") && (
                <Notice
                  tone={ended === "cancelled" ? "neutral" : "danger"}
                  onDismiss={() => setDismissed(run.id)}
                >
                  {describeEnding(ended, run.error)}
                </Notice>
              )}
            {problem && !problem.quiet && !running && (
              <Notice tone="neutral" icon="warning" title={problem.title}>
                {problem.text}
              </Notice>
            )}
          </div>
        )}
        {running && run ? (
          <div className="mt-2.5 flex h-9 items-center gap-2 bg-accent-soft px-3">
            <LoadingMark size={12} />
            <span className="text-label">
              {stopping === run.id ? "Stopping" : "Working"}
            </span>
            <Elapsed since={run.started} />
            <span className="flex-1" />
            <Button
              variant="secondary"
              size="sm"
              disabled={stopping === run.id}
              onClick={() => void stop()}
            >
              <Icon name="stop" />
              Stop
            </Button>
          </div>
        ) : (
          <div className="flex gap-2 px-3 pt-2.5 pb-3">
            <Tooltip content="Preview request" side="top">
              <Button
                variant="secondary"
                size="lg"
                icon
                aria-label="Preview request"
                disabled={problem !== null}
                onClick={() => setPreviewing(true)}
              >
                <Icon name="eye" />
              </Button>
            </Tooltip>
            <span
              title={problem?.title ?? problem?.text}
              className="flex min-w-0 flex-1"
            >
              <Button
                variant="primary"
                size="lg"
                className="flex-1"
                disabled={problem !== null || starting}
                onClick={() => void generate()}
              >
                {starting && <LoadingMark />}
                {starting ? "Starting" : "Generate"}
              </Button>
            </span>
          </div>
        )}
      </footer>
      <RequestPreview
        open={previewing}
        request={
          previewing && problem === null
            ? requestOf(target, draft.prompt, options, resolved, methods)
            : null
        }
        source={target.image ? target : null}
        onClose={() => setPreviewing(false)}
        onGenerate={() => {
          setPreviewing(false);
          void generate();
        }}
      />
    </div>
  );
}

/** The pane on the right: the way of making an image, and under it what that way asks for. */
export function RequestPane({
  listing,
  image,
  shown,
  runs,
  onCreated,
  onChanged,
  onView,
}: {
  listing: ImageListing | null;
  /** The image in view, which a request edits; none for a new image. */
  image: ImageSummary | null;
  shown: Shown | null;
  runs: Runs;
  /** Called with a new image's name once the request that creates it has started. */
  onCreated: (name: string) => Promise<void>;
  /** Called once a request on the image in view has started, so it is listed again. */
  onChanged: () => Promise<void>;
  /** Show the version with this id; null for what the image's file holds. */
  onView: (version: string | null) => void;
}) {
  const { error } = useAppState();
  const { methods, error: unread } = useMethods();
  return (
    <aside
      aria-label="Request"
      className="flex h-full min-w-0 flex-col bg-panel"
    >
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-line pr-2 pl-3">
        <span className="text-label text-ink-muted">Method</span>
        <Segmented<AppMethod>
          label="Method"
          value="model"
          onChange={() => {}}
          options={[
            { value: "model", label: "Image model" },
            { value: "svg", label: "SVG", disabled: "Not in the app yet" },
          ]}
        />
      </header>
      {error && <Notice className="m-2">{error}</Notice>}
      {unread && <Notice className="m-2">{unread}</Notice>}
      {methods ? (
        <RequestForm
          methods={methods}
          listing={listing}
          image={image}
          shown={shown}
          runs={runs}
          onCreated={onCreated}
          onChanged={onChanged}
          onView={onView}
        />
      ) : (
        <div className="min-h-0 flex-1" />
      )}
    </aside>
  );
}
