import { useEffect, useState } from "react";

import { DrawPane } from "@/components/DrawPane";
import { ImageModelSelect } from "@/components/ImageModelPicker";
import { ImagePane } from "@/components/ImagePane";
import { NewImageName } from "@/components/NewImageName";
import { PromptPicker } from "@/components/PromptPicker";
import { References } from "@/components/References";
import { RequestPreview } from "@/components/RequestPreview";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { FormRow } from "@/components/ui/form-row";
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
import { useDurations, useSourceFrame } from "@/lib/frames";
import {
  clearGuides,
  clearMask,
  setTool,
  useCanvas,
  useGuides,
  type CanvasMode,
} from "@/lib/canvas";
import { moveDraft, updateDraft, useDraft } from "@/lib/drafts";
import { describe, describeEnding } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { sentMark } from "@/lib/marks";
import { useMethods } from "@/lib/methods";
import { earlierPrompts } from "@/lib/prompts";
import {
  addFiles,
  clearReferences,
  imageFiles,
  sentReferences,
  uploadMask,
  useReferences,
} from "@/lib/references";
import {
  CHATGPT_LABEL,
  folderIn,
  FRAME_SIZES,
  freeName,
  freeNewName,
  kindOf,
  makesNew,
  modelLabel,
  nameFrom,
  pickedModel,
  problemOf,
  qualityLabel,
  referenceRoom,
  requestOf,
  resolve,
  sendsSource,
  SIZES,
  sourcePicture,
  stem,
  stillFormats,
  typedName,
  type Kind,
  type Resolved,
  type SentGuide,
  type Source,
  type Target,
} from "@/lib/request";
import { readRunsAgain, type Runs } from "@/lib/runs";
import { updateSettings, useSettings } from "@/lib/settings";
import { closeSheet, openSheet, useSheet, type Sheet } from "@/lib/sheets";
import { flushAppState, updateAppState, useAppState } from "@/lib/state";
import { useElapsed } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { Shown } from "@/lib/viewed";

const BY_CHATGPT = "Chosen by ChatGPT";
const KEEPS_FORMAT = "An edit keeps the image's format";
const NO_TRANSPARENCY = "JPEG has no transparency";
const AS_GIF = "An animation is saved as a GIF";
const OPAQUE_ANIMATION = "An animation has no transparent background";
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

/** What the request is for, the image in view or a new image and its name, and the model it goes to. */
function TargetBlock({
  target,
  newKey,
  listing,
  folder,
  typed,
  resolved,
  methods,
  onUseInNew,
}: {
  target: Target;
  /** What a new image's request is kept under. */
  newKey: string;
  listing: ImageListing | null;
  /** The folder a new image goes in, "" for the top. */
  folder: string;
  /** A new image's name as it stands in the field. */
  typed: string;
  resolved: Resolved;
  methods: ImageMethods;
  onUseInNew: (name: string) => void;
}) {
  const source = target.image ? target : target.from;
  const shown = source ? source.shown : null;
  return (
    <div className="flex flex-col gap-2 border-b border-line p-3">
      <div className="flex items-center gap-2.5">
        {source && shown ? (
          <>
            <Thumb
              picture={sourcePicture(source, true)}
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
                  {source.frame !== null && (
                    <span>frame {source.frame + 1}</span>
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
          <NewImageName
            draftKey={newKey}
            listing={listing}
            folder={folder}
            typed={typed}
            extension={resolved.format}
          />
        )}
      </div>
      <FormRow label="Model">
        <ImageModelSelect
          value={resolved.model}
          onChange={(model) => update({ model })}
          methods={methods}
        />
      </FormRow>
    </div>
  );
}

/**
 * What the image comes out as. An option the picked model, the image's format, or an animation does not take is
 * greyed out.
 */
function Output({
  options,
  resolved,
  methods,
  target,
  onKind,
}: {
  options: AppImageRequest;
  resolved: Resolved;
  methods: ImageMethods;
  target: Target;
  /** Pick what the request makes: a still image, or an animation. */
  onKind: (kind: Kind) => void;
}) {
  const { advanced } = useSettings().settings;
  const { openai, chatgpt } = methods;
  const byChatGPT = resolved.method === "chatgpt" ? BY_CHATGPT : undefined;
  const source = target.image ? target.shown : null;
  const animated = resolved.kind === "animation";
  const sizes = animated ? FRAME_SIZES : SIZES;
  const size = resolved.size ? resolved.size.join("x") : AUTO;
  // An animation being edited keeps its own length until another is set, so that is what the fields start on.
  const kept = animated && source !== null && source.frames > 1;
  const durations = useDurations(source?.picture ?? null, kept);
  const within = (value: number, [low, high]: [number, number]) =>
    Math.min(high, Math.max(low, value));
  const frames =
    resolved.frames ??
    within(kept ? source.frames : options.frames, openai.frames);
  const frameMs =
    resolved.frameMs ??
    within(durations?.[0] ?? options.frame_ms, openai.frame_ms);
  const codexModel = chatgpt.models.find(
    (model) => model.id === resolved.codexModel,
  );
  return (
    <div className="flex flex-col gap-2">
      <FormRow label="Type">
        <Segmented<Kind>
          label="Type"
          size="sm"
          full
          className="flex-1"
          value={resolved.kind}
          onChange={onKind}
          options={[
            { value: "image", label: "Image" },
            {
              value: "animation",
              label: "Animation",
              disabled:
                byChatGPT && `${CHATGPT_LABEL} does not make animations`,
            },
          ]}
        />
      </FormRow>
      <FormRow label={animated ? "Frame size" : "Size"} off={byChatGPT}>
        <Select
          label={animated ? "Frame size" : "Size"}
          value={size}
          disabled={byChatGPT !== undefined}
          onChange={(picked) => {
            const size =
              sizes.find((each) => each.size.join("x") === picked)?.size ??
              null;
            if (target.image) {
              updateDraft(target.image.name, { size });
            } else {
              update(animated ? { frame_size: size } : { size });
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
            ...sizes.map((each) => ({
              value: each.size.join("x"),
              label: each.label,
              aside: dimensions(...each.size),
            })),
          ]}
        />
      </FormRow>
      {animated && (
        <>
          <FormRow label="Frames">
            <ValueField
              label="Count"
              className="flex-1"
              value={frames}
              min={openai.frames[0]}
              max={openai.frames[1]}
              onChange={(frames) =>
                target.image
                  ? updateDraft(target.image.name, { frames })
                  : update({ frames })
              }
            />
          </FormRow>
          <FormRow label="Frame time">
            <ValueField
              label="Each"
              className="flex-1"
              value={frameMs}
              min={openai.frame_ms[0]}
              max={openai.frame_ms[1]}
              step={10}
              unit="ms"
              onChange={(frameMs) =>
                target.image
                  ? updateDraft(target.image.name, { frameMs })
                  : update({ frame_ms: frameMs })
              }
            />
          </FormRow>
        </>
      )}
      <FormRow label="Quality" off={byChatGPT}>
        <Select
          label="Quality"
          value={options.quality}
          disabled={byChatGPT !== undefined}
          onChange={(quality) => update({ quality })}
          items={openai.qualities.map((quality) => ({
            value: quality,
            label: qualityLabel(quality),
          }))}
        />
      </FormRow>
      <FormRow label="Format">
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
            disabled: animated
              ? AS_GIF
              : target.image
                ? KEEPS_FORMAT
                : (byChatGPT ??
                  (format === ".jpg" && options.background === "transparent"
                    ? NO_TRANSPARENCY
                    : undefined)),
          }))}
        />
      </FormRow>
      <FormRow label="Background">
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
                : background === "transparent" && animated
                  ? OPAQUE_ANIMATION
                  : background === "transparent" &&
                      target.image &&
                      !resolved.transparency
                    ? NO_TRANSPARENCY
                    : undefined,
          }))}
        />
      </FormRow>
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
          <FormRow label="Complexity" off={byChatGPT}>
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
          </FormRow>
          <FormRow
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
          </FormRow>
          {resolved.method === "chatgpt" && (
            <>
              <FormRow label="Codex model">
                <Select
                  label="Codex model"
                  value={resolved.codexModel}
                  onChange={(codex_model) => update({ codex_model })}
                  items={chatgpt.models.map((model) => ({
                    value: model.id,
                    label: model.label,
                  }))}
                />
              </FormRow>
              <FormRow label="Reasoning">
                <Select
                  label="Reasoning effort"
                  value={resolved.reasoningEffort}
                  onChange={(reasoning_effort) => update({ reasoning_effort })}
                  items={(
                    codexModel?.reasoning_efforts ?? [resolved.reasoningEffort]
                  ).map((effort) => ({
                    value: effort,
                    label: QUALITIES[effort] ?? titled(effort),
                  }))}
                />
              </FormRow>
            </>
          )}
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

/** The request to an image model: what it is for, the prompt, what comes out, and Generate, or Stop while it works. */
function RequestForm({
  methods,
  listing,
  image,
  shown,
  runs,
  mode,
  newKey,
  onUseInNew,
  onCreated,
  onChanged,
  onView,
  sheet,
  onBack,
}: {
  methods: ImageMethods;
  listing: ImageListing | null;
  image: ImageSummary | null;
  shown: Shown | null;
  runs: Runs;
  mode: CanvasMode | null;
  newKey: string;
  onUseInNew: (name: string) => void;
  onCreated: (name: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onView: (version: string | null) => void;
  /** What the form is open on, over the image's conversation. */
  sheet: Sheet;
  /** Go back to the conversation. */
  onBack: () => void;
}) {
  const { state } = useAppState();
  const options = state.request;
  const key = image ? image.name : newKey;
  const draft = useDraft(key);
  const references = useReferences(key);
  const guides = useGuides(key, shown?.picture?.key ?? null);
  const frame = useSourceFrame(image, shown, mode);
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

  const model = pickedModel(options.model, methods);
  const kind = kindOf(image, draft.kind, options, model);
  // A request that cannot change the image in view, or that makes another type of image, makes a new image from it,
  // which takes what a new image is picked.
  const crossing =
    image !== null && makesNew(image, "model", model, methods, kind);
  // An animation of one frame has no length of its own for an edit to keep.
  const long = shown !== null && shown.frames > 1;
  const resolved = resolve(options, methods, crossing ? null : image, kind, {
    size: draft.size,
    frames: draft.frames ?? (long ? null : options.frames),
    frameMs: draft.frameMs ?? (long ? null : options.frame_ms),
  });
  const folder = folderIn(listing, draft.folder);
  const typed = draft.name ?? freeNewName(listing, resolved.format, folder);
  // Nothing shows yet of an image whose first call has not made it, so there is no source to edit.
  const source: Source | null =
    image && shown && shown.picture !== null ? { image, shown, frame } : null;
  const unmade = image !== null && source === null;
  const target: Target = unmade
    ? { image: null, name: stem(image.name), from: null }
    : source
      ? crossing
        ? {
            image: null,
            name: freeName(
              listing,
              resolved.format,
              nameFrom(source, resolved.kind),
            ),
            from: source,
          }
        : source
      : {
          image: null,
          name: typedName(typed, methods.openai.formats, folder),
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
    // The image the call makes is already listed, under the name the call gives it.
    unmade ? null : listing,
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
      const request = requestOf(
        target,
        draft.prompt,
        options,
        resolved,
        methods,
        guide(mask?.upload ?? null),
      );
      const started = await generateImage(request);
      watched.add(started.run_id);
      if (unmade) {
        clearReferences(key);
        await onChanged();
        onBack();
      } else if (target.image) {
        // What guided the call went with it. The next message to the agent starts with nothing attached.
        clearGuides(target.image.name);
        clearReferences(key);
        // What the run makes lands in the image's file, so that is what shows while it works.
        onView(null);
        await onChanged();
        onBack();
      } else {
        // What the new image was made from says nothing about how it is changed next.
        clearReferences(key);
        moveDraft(key, started.name);
        await onCreated(started.name);
        onBack();
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
      <header className="flex h-9 shrink-0 items-center gap-1.5 border-b border-line pr-3 pl-1.5">
        <Tooltip content="Back to the conversation" side="bottom">
          <Button
            size="sm"
            icon
            aria-label="Back to the conversation"
            onClick={onBack}
          >
            <Icon name="chevron" className="rotate-90" />
          </Button>
        </Tooltip>
        <h2 className="text-label">{sheet.title}</h2>
        <span className="flex-1" />
        <span className="truncate text-caption text-ink-muted">
          Sent as written, with no agent
        </span>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <TargetBlock
          target={target}
          newKey={newKey}
          listing={listing}
          folder={folder}
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
          edited={shown && !shown.file ? (shown.version?.id ?? null) : null}
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
            onKind={(picked) =>
              image
                ? updateDraft(key, { kind: picked })
                : update({ kind: picked })
            }
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
        from={target.from ?? null}
        references={references}
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
  newKey,
  method,
  onMethod,
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
  /** What the request for a new image is kept under. */
  newKey: string;
  /** The way the image is made, an image model or drawing an SVG. */
  method: AppMethod;
  onMethod: (method: AppMethod) => void;
  /** Start a new image with the image named as its first reference. */
  onUseInNew: (name: string) => void;
  /** Called with a new image's name once the request that creates it has started. */
  onCreated: (name: string) => Promise<void>;
  /** Called once a request on the image in view has started, so it is listed again. */
  onChanged: () => Promise<void>;
  /** Show the version with this id; null for what the image's file holds. */
  onView: (version: string | null) => void;
}) {
  const { error } = useAppState();
  const { methods, error: unread } = useMethods();
  const drawing = method === "svg";
  const key = image ? image.name : newKey;
  // The editor of an image call, for the image it was opened on; another image in view leaves it.
  const opened = useSheet(key);
  const sheet = drawing ? null : opened;
  const working =
    image?.status === "running" || image?.design?.status === "running";

  const leaveSheet = () => {
    if (sheet?.filled) {
      updateDraft(key, { prompt: "" });
      clearReferences(key);
    }
    closeSheet();
    readRunsAgain();
  };

  return (
    <aside
      aria-label="Conversation"
      className="flex h-full min-w-0 flex-col bg-panel"
    >
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-line pr-2 pl-3">
        <span className="text-label text-ink-muted">Method</span>
        <Segmented<AppMethod>
          label="Method"
          value={method}
          onChange={onMethod}
          options={[
            { value: "model", label: "Image model" },
            { value: "svg", label: "SVG" },
          ]}
        />
        <span className="flex-1" />
        {methods && !drawing && (
          <Tooltip
            content={
              sheet
                ? "Back to the conversation"
                : "Write the image call yourself, sent with no agent"
            }
            side="bottom"
          >
            <Button
              size="sm"
              aria-pressed={sheet !== null}
              disabled={sheet === null && working}
              onClick={() =>
                sheet
                  ? leaveSheet()
                  : openSheet(key, {
                      title: "Your image call",
                      filled: false,
                    })
              }
              className="min-w-0"
            >
              <Icon name="sliders" />
              <span className="truncate">Write image call</span>
            </Button>
          </Tooltip>
        )}
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
          newKey={newKey}
          onUseInNew={onUseInNew}
          onCreated={onCreated}
          onChanged={onChanged}
          onView={onView}
        />
      ) : methods && sheet ? (
        <RequestForm
          methods={methods}
          listing={listing}
          image={image}
          shown={shown}
          runs={runs}
          mode={mode}
          newKey={newKey}
          onUseInNew={onUseInNew}
          onCreated={onCreated}
          onChanged={onChanged}
          onView={onView}
          sheet={sheet}
          onBack={leaveSheet}
        />
      ) : methods ? (
        <ImagePane
          key={key}
          methods={methods}
          listing={listing}
          image={image}
          shown={shown}
          runs={runs}
          mode={mode}
          newKey={newKey}
          onCreated={onCreated}
          onChanged={onChanged}
          onView={onView}
          onSheet={(filled) => openSheet(key, filled)}
        />
      ) : (
        <div className="min-h-0 flex-1" />
      )}
    </aside>
  );
}
