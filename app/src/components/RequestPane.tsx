import { useEffect, useState, type ReactNode } from "react";

import { DrawPane } from "@/components/DrawPane";
import { PromptPicker } from "@/components/PromptPicker";
import { References } from "@/components/References";
import { RequestPreview } from "@/components/RequestPreview";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
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
import {
  clearGuides,
  clearMask,
  setTool,
  useCanvas,
  useGuides,
  type CanvasMode,
} from "@/lib/canvas";
import { moveDraft, NEW_IMAGE, updateDraft, useDraft } from "@/lib/drafts";
import { describe, describeEnding } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { openKeyDialog, useKey } from "@/lib/key";
import { sentMark } from "@/lib/marks";
import { useMethods } from "@/lib/methods";
import { earlierPrompts } from "@/lib/prompts";
import {
  addFiles,
  clearReferences,
  imageFiles,
  sentReferences,
  type Reference,
  settleReferences,
  uploadMask,
  useReferences,
} from "@/lib/references";
import {
  CHATGPT,
  CHATGPT_LABEL,
  freeName,
  makesNew,
  modelLabel,
  pickedModel,
  problemOf,
  referenceRoom,
  requestOf,
  resolve,
  sendsSource,
  SIZES,
  sourcePath,
  stem,
  stillFormats,
  typedName,
  type Resolved,
  type SentGuide,
  type Target,
} from "@/lib/request";
import type { Runs } from "@/lib/runs";
import { updateSettings, useSettings } from "@/lib/settings";
import { flushAppState, updateAppState, useAppState } from "@/lib/state";
import { useElapsed } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { Shown } from "@/lib/viewed";

const BY_CHATGPT = "Chosen by ChatGPT";
const ONLY_CHATGPT = "Only with ChatGPT";
const KEEPS_FORMAT = "An edit keeps the image's format";
const NO_TRANSPARENCY = "JPEG has no transparency";
const AUTO = "auto";
// In the model list, opens the dialog about the key rather than picking a model.
const SET_KEY = "set-openai-key";

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
  onUseInNew,
}: {
  target: Target;
  /** A new image's name as it stands in the field. */
  typed: string;
  resolved: Resolved;
  methods: ImageMethods;
  onUseInNew: (name: string) => void;
}) {
  const { openai, chatgpt } = methods;
  const key = useKey();
  const source = target.image ? target : target.from;
  const shown = source ? source.shown : null;
  return (
    <div className="flex flex-col gap-2 border-b border-line p-3">
      <div className="flex items-center gap-2.5">
        {source && shown ? (
          <>
            <Thumb
              picture={shown.picture && { ...shown.picture, small: true }}
              shape={shown}
              className="size-11"
            />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="truncate mono-value">{source.image.name}</span>
              {target.image ? (
                <span className="flex gap-2 mono-annotation text-ink-muted">
                  {shown.version && <span>{shown.version.id}</span>}
                  {shown.width !== null && shown.height !== null && (
                    <span>{dimensions(shown.width, shown.height)}</span>
                  )}
                </span>
              ) : (
                <span className="flex min-w-0 gap-1.5 text-caption text-ink-muted">
                  Makes
                  <span className="truncate mono-value text-ink">
                    {target.name}
                    {resolved.format}
                  </span>
                </span>
              )}
            </div>
            <Menu>
              <MenuTrigger
                render={
                  <Button size="sm" icon aria-label="More for the source" />
                }
              >
                <Icon name="more" />
              </MenuTrigger>
              <MenuContent align="end">
                <MenuItem onClick={() => onUseInNew(source.image.name)}>
                  <Icon name="image" />
                  Use as a reference instead
                </MenuItem>
              </MenuContent>
            </Menu>
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
          onChange={(model) =>
            model === SET_KEY ? openKeyDialog() : update({ model })
          }
          items={[
            ...openai.models.map((model) => ({
              value: model.id,
              label: model.label,
              group: "OpenAI API",
              disabled: openai.ready
                ? undefined
                : (openai.problem ?? "Not set up"),
            })),
            // Where the person looks when the models are greyed out for want of a key.
            ...(key.status?.source === null
              ? [
                  {
                    value: SET_KEY,
                    label: "Set API key...",
                    group: "OpenAI API",
                  },
                ]
              : []),
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
  const { advanced } = useSettings().settings;
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
        onClick={() =>
          updateSettings((current) => ({
            ...current,
            advanced: !current.advanced,
          }))
        }
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

/** The mask being painted on the canvas: how much of the image it covers, and the tools that paint it. */
function MaskSection({
  name,
  painted,
  open,
  onOpenChange,
}: {
  name: string;
  /** The share of the image the mask covers. */
  painted: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { tool } = useCanvas();
  return (
    <Section
      title="Mask"
      open={open}
      onOpenChange={onOpenChange}
      aside={
        <span className="pr-1 mono-annotation text-ink-muted">
          {painted > 0
            ? `${Math.max(1, Math.round(painted * 100))}% of the image`
            : "nothing painted"}
        </span>
      }
    >
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          aria-pressed={tool === "brush"}
          onClick={() => setTool("brush")}
          className="aria-pressed:border-accent-ink aria-pressed:bg-accent-soft"
        >
          <Icon name="area" />
          Paint
        </Button>
        <Button
          variant="secondary"
          size="sm"
          aria-pressed={tool === "eraser"}
          onClick={() => setTool("eraser")}
          className="aria-pressed:border-accent-ink aria-pressed:bg-accent-soft"
        >
          <Icon name="eraser" />
          Erase
        </Button>
        <span className="flex-1" />
        {painted > 0 && (
          <Button size="sm" onClick={() => clearMask(name)}>
            Clear
          </Button>
        )}
      </div>
    </Section>
  );
}

/** The image a new one is made from, as the first of the references it is sent with. */
function sourceReference(from: {
  image: ImageSummary;
  shown: Shown;
}): Reference {
  return {
    id: "source",
    name: from.image.name,
    path: sourcePath(from),
    upload: null,
    thumb: null,
    state: "ready",
  };
}

/** The request to an image model: what it is for, the prompt, what comes out, and Generate, or Stop while it works. */
function RequestForm({
  methods,
  listing,
  image,
  shown,
  runs,
  mode,
  onUseInNew,
  onCreated,
  onChanged,
  onView,
}: {
  methods: ImageMethods;
  listing: ImageListing | null;
  image: ImageSummary | null;
  shown: Shown | null;
  runs: Runs;
  mode: CanvasMode | null;
  onUseInNew: (name: string) => void;
  onCreated: (name: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onView: (version: string | null) => void;
}) {
  const { state } = useAppState();
  const options = state.request;
  const key = image ? image.name : NEW_IMAGE;
  const draft = useDraft(key);
  const references = useReferences(key);
  const guides = useGuides(key, shown?.picture?.key ?? null);
  const [open, setOpen] = useState({
    prompt: true,
    mask: true,
    references: true,
    output: true,
  });
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  // While the request is previewed: the mask it would send, which is sent up before the library can say.
  const [previewing, setPreviewing] = useState<{
    mask: { upload: string; url: string } | null;
  } | null>(null);

  // A model that cannot change the image in view makes a new image from it, which takes what a new image is picked.
  const crossing =
    image !== null &&
    makesNew(image, "model", pickedModel(options, methods), methods);
  const resolved = resolve(
    options,
    methods,
    crossing ? null : image,
    draft.size,
  );
  const typed = draft.name ?? freeName(listing, resolved.format);
  const target: Target =
    image && shown
      ? crossing
        ? {
            image: null,
            name: freeName(listing, resolved.format, stem(image.name)),
            from: { image, shown },
          }
        : { image, shown }
      : {
          image: null,
          name: typedName(typed, stillFormats(methods)),
          from: null,
        };
  // Only the guide of the mode the canvas is in goes out, since a request takes marks or a mask and not both.
  const marks = image && mode === "markup" ? guides.marks : [];
  const masked = image !== null && mode === "mask" && guides.painted > 0;
  const room = referenceRoom(
    resolved,
    methods,
    sendsSource(target),
    marks.length > 0,
  );
  const full =
    references.length >= room
      ? `${modelLabel(resolved, methods)} takes ${methods[resolved.method].max_images} images`
      : null;
  const problem = problemOf(
    target,
    draft.prompt,
    resolved,
    methods,
    listing,
    references,
    room,
  );
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

  const setPrompt = (prompt: string) => updateDraft(key, { prompt });

  /** The mask painted on the image in view, sent up for a request to take; null when the request has none. */
  const sendMask = async () =>
    masked && image && shown && shown.width !== null && shown.height !== null
      ? uploadMask(image.name, shown.width, shown.height)
      : null;

  const guide = (mask: string | null): SentGuide => ({
    references: sentReferences(references),
    marks: marks.map(sentMark),
    mask,
  });

  const generate = async () => {
    if (problem !== null || starting || running) {
      return;
    }
    setStarting(true);
    setFailure(null);
    try {
      // The server sends only references it knows the app offers, a pin among them once the pin is saved.
      await flushAppState();
      const mask = await sendMask();
      const sent = references;
      const started = await generateImage(
        requestOf(
          target,
          draft.prompt,
          options,
          resolved,
          methods,
          guide(mask?.upload ?? null),
        ),
      );
      watched.add(started.run_id);
      if (target.image) {
        // The marks and the mask were for this request. The references stay for the next one.
        clearGuides(target.image.name);
        settleReferences(key, sent, started.references);
        // What the run makes lands in the image's file, so that is what shows while it works.
        onView(null);
        await onChanged();
      } else {
        // What the new image was made from says nothing about how it is changed next.
        clearReferences(key);
        moveDraft(key, started.name);
        await onCreated(started.name);
      }
    } catch (cause) {
      setFailure(`The request did not start. ${describe(cause)}`);
    } finally {
      setStarting(false);
    }
  };

  const preview = async () => {
    setFailure(null);
    try {
      await flushAppState();
      setPreviewing({ mask: await sendMask() });
    } catch (cause) {
      setFailure(`Could not preview the request. ${describe(cause)}`);
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
      onPaste={(event) => {
        const files = imageFiles(event.clipboardData);
        if (files.length > 0) {
          event.preventDefault();
          addFiles(key, files, room);
        }
      }}
    >
      <div className="min-h-0 flex-1 overflow-y-auto">
        <TargetBlock
          target={target}
          typed={typed}
          resolved={resolved}
          methods={methods}
          onUseInNew={onUseInNew}
        />
        <Section
          title="Prompt"
          open={open.prompt}
          onOpenChange={(prompt) => setOpen({ ...open, prompt })}
          aside={
            <PromptPicker
              editing={target.image !== null}
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
        {image && mode === "mask" && (
          <MaskSection
            name={image.name}
            painted={guides.painted}
            open={open.mask}
            onOpenChange={(mask) => setOpen({ ...open, mask })}
          />
        )}
        <References
          open={open.references}
          onOpenChange={(shown) => setOpen({ ...open, references: shown })}
          target={key}
          references={references}
          room={room}
          full={full}
          first={
            (sendsSource(target) ? 2 : 1) +
            (resolved.method === "chatgpt" && marks.length > 0 ? 1 : 0)
          }
          listing={listing}
          source={image?.name ?? null}
          onError={setFailure}
        />
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
                onClick={() => void preview()}
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
        open={previewing !== null}
        request={
          previewing && problem === null
            ? requestOf(
                target,
                draft.prompt,
                options,
                resolved,
                methods,
                guide(previewing.mask?.upload ?? null),
              )
            : null
        }
        source={target.image ? target : null}
        references={
          target.from
            ? [sourceReference(target.from), ...references]
            : references
        }
        marks={marks}
        mask={previewing?.mask?.url ?? null}
        onClose={() => setPreviewing(null)}
        onGenerate={() => {
          setPreviewing(null);
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
  mode,
  onUseInNew,
  onCreated,
  onChanged,
  onView,
}: {
  listing: ImageListing | null;
  /** The image in view, which a request edits; none for a new image. */
  image: ImageSummary | null;
  shown: Shown | null;
  runs: Runs;
  /** What on the canvas guides the request: its marks, or its mask; null when the image takes neither. */
  mode: CanvasMode | null;
  /** Start a new image with the image named as its first reference. */
  onUseInNew: (name: string) => void;
  /** Called with a new image's name once the request that creates it has started. */
  onCreated: (name: string) => Promise<void>;
  /** Called once a request on the image in view has started, so it is listed again. */
  onChanged: () => Promise<void>;
  /** Show the version with this id; null for what the image's file holds. */
  onView: (version: string | null) => void;
}) {
  const { state, error } = useAppState();
  const { methods, error: unread } = useMethods();
  const drawing = state.method === "svg";
  return (
    <aside
      aria-label={drawing ? "Conversation" : "Request"}
      className="flex h-full min-w-0 flex-col bg-panel"
    >
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-line pr-2 pl-3">
        <span className="text-label text-ink-muted">Method</span>
        <Segmented<AppMethod>
          label="Method"
          value={state.method}
          onChange={(method) =>
            updateAppState((current) => ({ ...current, method }))
          }
          options={[
            { value: "model", label: "Image model" },
            { value: "svg", label: "SVG" },
          ]}
        />
      </header>
      {error && <Notice className="m-2">{error}</Notice>}
      {unread && <Notice className="m-2">{unread}</Notice>}
      {methods && drawing ? (
        <DrawPane
          key={image?.name ?? ""}
          methods={methods}
          listing={listing}
          image={image}
          shown={shown}
          runs={runs}
          mode={mode}
          onUseInNew={onUseInNew}
          onCreated={onCreated}
          onChanged={onChanged}
          onView={onView}
        />
      ) : methods ? (
        <RequestForm
          methods={methods}
          listing={listing}
          image={image}
          shown={shown}
          runs={runs}
          mode={mode}
          onUseInNew={onUseInNew}
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
