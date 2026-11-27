import { useState, type ClipboardEvent, type ReactNode } from "react";

import { AgentPicker, AgentRows } from "@/components/activity/AgentPicker";
import { Composer } from "@/components/activity/Composer";
import { LiveStrip } from "@/components/activity/RunParts";
import { Thread } from "@/components/activity/Thread";
import { NewImageName } from "@/components/NewImageName";
import { PromptPicker } from "@/components/PromptPicker";
import { ReferenceLibrary } from "@/components/ReferenceLibrary";
import { References } from "@/components/References";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { FormRow } from "@/components/ui/form-row";
import { Icon } from "@/components/ui/icon";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Section } from "@/components/ui/section";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Thumb } from "@/components/ui/thumb";
import { Tooltip } from "@/components/ui/tooltip";
import {
  cancelImage,
  drawSvgImage,
  steerSvgImage,
  type AppSvgRequest,
  type ImageListing,
  type ImageMethods,
  type ImageSummary,
} from "@/lib/api";
import {
  clearGuides,
  clearMarks,
  removeMark,
  useCanvas,
  useGuides,
  type CanvasMode,
} from "@/lib/canvas";
import { draftOf, dropDraft, updateDraft, useDraft } from "@/lib/drafts";
import {
  agentOf,
  budgetsOf,
  CANVASES,
  changeDrawing,
  conversationOf,
  drawOf,
  sentDrawing,
  sizeOf,
  useDrawing,
  type Budgets,
} from "@/lib/drawing";
import { describe } from "@/lib/errors";
import { dimensions } from "@/lib/format";
import { useSourceFrame } from "@/lib/frames";
import { sentMark } from "@/lib/marks";
import { typedProblem } from "@/lib/paths";
import { earlierPrompts } from "@/lib/prompts";
import {
  addFiles,
  clearReferences,
  imageFiles,
  removeReference,
  sentReferences,
  useReferences,
} from "@/lib/references";
import {
  DRAWING,
  folderIn,
  freeName,
  freeNewName,
  sourcePicture,
  stem,
  typedName,
  type Problem,
  type Source,
  type Target,
} from "@/lib/request";
import type { Runs } from "@/lib/runs";
import { sessionOf, setResume, useResume } from "@/lib/sessions";
import { flushAppState, updateAppState, useAppState } from "@/lib/state";
import { currentCall, runsOf, sentTurn, useSentTurn } from "@/lib/thread";
import type { Shown } from "@/lib/viewed";

const MATCH = "match";
const CUSTOM = "custom";
const FIXED = "fixed";
const KB = 1024;
const MINUTE = 60;
const FIXED_CANVAS =
  "A drawing keeps its canvas. Ask for another in a message.";

function updateSvg(change: Partial<AppSvgRequest>) {
  updateAppState((current) => ({
    ...current,
    svg: { ...current.svg, ...change },
  }));
}

function same(a: [number, number], b: [number, number] | null): boolean {
  return b !== null && a[0] === b[0] && a[1] === b[1];
}

/**
 * What a new drawing will be called, or the drawing a request changes, and the image a new one is drawn from, over
 * what else the request is picked with.
 */
function DrawTarget({
  target,
  newKey,
  listing,
  folder,
  typed,
  onUseInNew,
  children,
}: {
  target: Target;
  /** What a new drawing's request is kept under. */
  newKey: string;
  listing: ImageListing | null;
  /** The folder a new drawing goes in, "" for the top. */
  folder: string;
  /** A new drawing's name as it stands in the field. */
  typed: string;
  onUseInNew: (name: string) => void;
  children?: ReactNode;
}) {
  const source: Source | null = target.image ? target : target.from;
  return (
    <div className="flex shrink-0 flex-col gap-2 border-b border-line p-3">
      <div className="flex items-center gap-2.5">
        {source ? (
          <>
            <Thumb
              picture={sourcePicture(source, true)}
              shape={source.shown}
              className="size-11"
            />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="truncate mono-value">{source.image.name}</span>
              {target.image ? (
                <span className="flex gap-2 mono-annotation text-ink-muted">
                  {source.shown.version && (
                    <span>{source.shown.version.id}</span>
                  )}
                  {source.shown.width !== null &&
                    source.shown.height !== null && (
                      <span>
                        {dimensions(source.shown.width, source.shown.height)}
                      </span>
                    )}
                </span>
              ) : (
                <span className="flex min-w-0 gap-1.5 text-caption text-ink-muted">
                  Makes
                  <span className="truncate mono-value text-ink">
                    {target.name}
                    {DRAWING}
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
            extension={DRAWING}
          />
        )}
      </div>
      {children}
    </div>
  );
}

/** A number in a unit that is `scale` of it, as it reads; empty for null. */
function scaled(number: number | null, scale: number): string {
  return number === null
    ? ""
    : String(Math.round((number / scale) * 100) / 100);
}

/**
 * A number typed in, in `unit`, which is `scale` of what it stands for; left empty, it is null. What was typed stays
 * as typed while it says the same number, so a half-typed one such as `2.` is not rewritten.
 */
function NumberField({
  label,
  value,
  unit,
  scale = 1,
  empty,
  onChange,
}: {
  label: string;
  value: number | null;
  unit?: string;
  scale?: number;
  /** What an empty field means, shown in it and on the button that empties it; without one, it takes no empty value. */
  empty?: string;
  onChange: (value: number | null) => void;
}) {
  const asText = (number: number | null) => scaled(number, scale);
  const parse = (typed: string): number | null | undefined => {
    if (typed.trim() === "") {
      return empty === undefined ? undefined : null;
    }
    const number = Number(typed);
    return number > 0 ? Math.max(1, Math.round(number * scale)) : undefined;
  };
  const [typed, setTyped] = useState(asText(value));
  const [last, setLast] = useState(value);
  if (value !== last) {
    setLast(value);
    if (parse(typed) !== value) {
      setTyped(asText(value));
    }
  }
  const invalid = parse(typed) === undefined;
  return (
    <label className="flex h-7 min-w-0 flex-1 items-center gap-1 rounded-sm border border-line-control bg-field px-2 focus-within:border-ink focus-within:bg-panel focus-within:focus-ring has-aria-invalid:border-danger">
      <input
        aria-label={label}
        aria-invalid={invalid || undefined}
        inputMode="decimal"
        autoComplete="off"
        placeholder={empty}
        value={typed}
        onChange={(event) => {
          setTyped(event.target.value);
          const parsed = parse(event.target.value);
          if (parsed !== undefined) {
            onChange(parsed);
          }
        }}
        className="w-full min-w-0 bg-transparent mono-value text-ink outline-none placeholder:font-sans placeholder:text-ink-muted"
      />
      {unit && (
        <span className="shrink-0 mono-value text-ink-muted">{unit}</span>
      )}
      {empty !== undefined && typed !== "" && (
        <Tooltip content={empty}>
          <button
            type="button"
            aria-label={`${empty} for ${label.toLowerCase()}`}
            onClick={() => {
              setTyped("");
              onChange(null);
            }}
            className="-mr-1 grid size-5 shrink-0 cursor-default place-items-center rounded-sm text-ink-muted hover:bg-hover hover:text-ink focus-visible:focus-ring focus-visible:outline-none"
          >
            <Icon name="close" />
          </button>
        </Tooltip>
      )}
    </label>
  );
}

type BudgetProps = {
  budgets: Budgets;
  /** Whether the canvas is the drawing's own, which a message can ask to change. */
  fixed: boolean;
  /** The size of the image a new drawing is made from, which it can match; null when there is none. */
  match: [number, number] | null;
  /** In seconds; null for no limit. */
  timeout: number | null;
  onChange: (change: Partial<Budgets>) => void;
};

/** What the drawing is held to, as rows of a form. The agent is told, and the drawing is measured against it. */
function BudgetRows({ budgets, fixed, match, timeout, onChange }: BudgetProps) {
  const [custom, setCustom] = useState(false);
  const preset = CANVASES.find(({ size }) => same(size, budgets.canvas));
  const choice = fixed
    ? FIXED
    : custom
      ? CUSTOM
      : match && same(budgets.canvas, match)
        ? MATCH
        : preset
          ? preset.size.join("x")
          : CUSTOM;
  const [width, height] = budgets.canvas;
  return (
    <>
      <FormRow label="Canvas" off={fixed ? FIXED_CANVAS : undefined}>
        <Select
          label="Canvas"
          value={choice}
          disabled={fixed}
          onChange={(value) => {
            setCustom(value === CUSTOM);
            if (value === MATCH && match) {
              onChange({ canvas: match });
            }
            const found = CANVASES.find(({ size }) => size.join("x") === value);
            if (found) {
              onChange({ canvas: found.size });
            }
          }}
          items={
            fixed
              ? [{ value: FIXED, label: dimensions(width, height) }]
              : [
                  ...(match
                    ? [
                        {
                          value: MATCH,
                          label: "Match source",
                          aside: dimensions(match[0], match[1]),
                        },
                      ]
                    : []),
                  ...CANVASES.map(({ label, size }) => ({
                    value: size.join("x"),
                    label,
                    aside: dimensions(size[0], size[1]),
                  })),
                  { value: CUSTOM, label: "Custom" },
                ]
          }
        />
      </FormRow>
      {choice === CUSTOM && (
        <FormRow label="">
          <NumberField
            label="Width"
            value={width}
            unit="w"
            onChange={(value) =>
              value !== null && onChange({ canvas: [value, height] })
            }
          />
          <NumberField
            label="Height"
            value={height}
            unit="h"
            onChange={(value) =>
              value !== null && onChange({ canvas: [width, value] })
            }
          />
        </FormRow>
      )}
      <FormRow label="File size">
        <NumberField
          label="File size"
          value={budgets.max_bytes}
          unit="KB"
          scale={KB}
          empty="No limit"
          onChange={(max_bytes) => onChange({ max_bytes })}
        />
      </FormRow>
      <FormRow label="Time limit">
        <NumberField
          label="Time limit"
          value={timeout}
          unit="min"
          scale={MINUTE}
          empty="No limit"
          onChange={(timeout_seconds) => updateSvg({ timeout_seconds })}
        />
      </FormRow>
    </>
  );
}

/** The budgets of a drawing already made, in a popover from the message box, with the limits set beside its name. */
function BudgetPicker(props: BudgetProps) {
  const { budgets, timeout } = props;
  const limits = [
    budgets.max_bytes !== null && `${scaled(budgets.max_bytes, KB)} KB`,
    timeout !== null && `${scaled(timeout, MINUTE)} min`,
  ].filter(Boolean);
  return (
    <Popover>
      <PopoverTrigger
        render={<Button size="sm" variant="ghost" className="min-w-0" />}
      >
        <Icon name="sliders" />
        Budget
        {limits.length > 0 && (
          <span className="truncate text-ink-muted">{limits.join(", ")}</span>
        )}
      </PopoverTrigger>
      <PopoverContent
        label="Budget"
        side="top"
        align="start"
        className="flex w-80 flex-col gap-2 p-3"
      >
        <BudgetRows {...props} />
      </PopoverContent>
    </Popover>
  );
}

/** Why the message cannot be sent as it stands; null when it can. */
function problemOf(
  target: Target,
  message: string,
  methods: ImageMethods,
  listing: ImageListing | null,
  references: { name: string; state: string }[],
  steering: boolean,
): Problem | null {
  if (!steering && !methods.svg.ready) {
    return {
      title: "No agent to draw with is set up where the app runs.",
      text: methods.svg.problem ?? "",
      quiet: false,
    };
  }
  if (!target.image) {
    if (target.name === "") {
      return { text: "Give the drawing a name.", quiet: true };
    }
    const typed = target.from === null && typedProblem(target.name, DRAWING);
    if (typed) {
      return { text: typed, quiet: false };
    }
    const wanted = `${target.name}${DRAWING}`.toLowerCase();
    if (listing?.images.some((image) => image.name.toLowerCase() === wanted)) {
      return { text: "Another image already has that name.", quiet: false };
    }
  }
  const failed = references.find((reference) => reference.state === "failed");
  if (failed) {
    return {
      text: `${failed.name} did not reach the app. Remove it and add it again.`,
      quiet: false,
    };
  }
  if (references.some((reference) => reference.state === "uploading")) {
    return { text: "A reference is still being added.", quiet: true };
  }
  return message.trim() === ""
    ? {
        text: target.image ? "Write a message." : "Describe the drawing.",
        quiet: true,
      }
    : null;
}

/**
 * Drawing an SVG with an agent. A new drawing is a form like an image model's request; one already made is a
 * conversation: its activity, and a message box that starts a run or, while one works, steers it.
 */
export function DrawPane({
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
}) {
  const { state } = useAppState();
  const options = state.svg;
  const key = image ? image.name : newKey;
  const draft = useDraft(key);
  const newDraft = useDraft(newKey);
  const references = useReferences(key);
  const guides = useGuides(key, shown?.picture?.key ?? null);
  const { numbered } = useCanvas();
  const drawing = useDrawing(key);
  const resume = useResume(key);
  const [picking, setPicking] = useState(false);
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [open, setOpen] = useState({
    prompt: true,
    references: true,
    budget: true,
  });

  const folder = folderIn(listing, newDraft.folder);
  const typed = newDraft.name ?? freeNewName(listing, DRAWING, folder);
  // A version the image's file does not hold is what is drawn from, so it is no reference.
  const edited = shown && !shown.file ? (shown.version?.id ?? null) : null;
  const editing = image !== null && image.name.toLowerCase().endsWith(DRAWING);
  // Of an animation, the frame picked is what the agent is shown.
  const frame = useSourceFrame(image, shown, mode);
  const from: Source | null =
    image && shown && !editing ? { image, shown, frame } : null;
  const target: Target =
    image && shown && editing
      ? { image, shown, frame: null }
      : from
        ? {
            image: null,
            name: freeName(listing, DRAWING, stem(from.image.name)),
            from,
          }
        : { image: null, name: typedName(typed, folder), from: null };
  const agent = agentOf(options, methods.svg);
  const session = sessionOf(
    editing ? (conversationOf(image)?.provider ?? null) : null,
    agent.provider,
    resume,
    "the drawing",
  );
  // A drawing and one made from an image in view keep what is changed for the session; a new one's are remembered.
  const local = editing || from !== null;
  const base = budgetsOf(editing ? image : null, from, options, methods);
  const budgets: Budgets = local ? { ...base, ...drawing.budgets } : base;
  const run = editing ? image.last_run : null;
  const running = editing && image.status === "running" && run !== null;
  const marks = editing && mode === "markup" ? guides.marks : [];
  const activity = editing ? runsOf(image, runs) : [];
  const turn = useSentTurn(key, activity);
  const problem = problemOf(
    target,
    draft.prompt,
    methods,
    listing,
    references,
    running,
  );
  const label = (model: string) =>
    methods.svg.models.find((each) => each.id === model)?.label ?? model;

  const changeBudgets = (change: Partial<Budgets>) => {
    if (local) {
      changeDrawing(key, { budgets: { ...drawing.budgets, ...change } });
    } else {
      updateSvg(change);
    }
  };

  const send = async () => {
    if (problem !== null || sending) {
      return;
    }
    setSending(true);
    setFailure(null);
    const message = draft.prompt;
    const sent = sentReferences(references);
    const sentMarks = marks.map((mark) => sentMark(mark, numbered));
    // A turn on the drawing shows in the thread at once, and the message leaves the box, while its run starts.
    const starts = target.image !== null && !running;
    if (starts) {
      turn.send(
        sentTurn(activity, message, sentMarks, {
          model: agent.model,
          reasoning_effort: agent.effort,
          resumed: session.continuing,
        }),
      );
      updateDraft(key, { prompt: "" });
    }
    try {
      // The server sends only references it knows the app offers, a pin among them once the pin is saved.
      await flushAppState();
      if (running && target.image) {
        await steerSvgImage({
          name: target.image.name,
          message,
          ...(sent.length > 0 ? { references: sent } : {}),
          ...(sentMarks.length > 0 ? { marks: sentMarks } : {}),
        });
        clearMarks(target.image.name);
      } else {
        const started = await drawSvgImage(
          drawOf(
            target,
            message,
            agent,
            options,
            budgets,
            drawing.budgets,
            session.continuing,
            sent,
            sentMarks,
          ),
        );
        sentDrawing(key);
        if (target.image) {
          turn.started(started.run_id);
          clearGuides(target.image.name);
          // What the run makes lands in the drawing's file, so that is what shows while it works.
          onView(null);
          await onChanged();
        } else {
          await onCreated(started.name);
        }
      }
      // What a message was given goes with it; the next one starts empty. A turn's left the box as it was sent, and
      // the next may be in it by now. A new drawing's request was for the drawing alone, which is in view from now on.
      if (!target.image && !target.from) {
        dropDraft(key);
      } else if (!starts) {
        updateDraft(key, { prompt: "" });
      }
      clearReferences(key);
    } catch (cause) {
      if (starts) {
        turn.failed();
        // The message goes back in the box, unless another was written there meanwhile.
        if (draftOf(key).prompt === "") {
          updateDraft(key, { prompt: message });
        }
      }
      setFailure(
        `${running ? "The message did not reach the agent." : "The drawing did not start."} ${describe(cause)}`,
      );
    } finally {
      setSending(false);
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
      setFailure(`Could not stop the drawing. ${describe(cause)}`);
    }
  };

  const notes = (failure || (problem && !problem.quiet)) && (
    <>
      {failure && <Notice onDismiss={() => setFailure(null)}>{failure}</Notice>}
      {problem && !problem.quiet && (
        <Notice tone="neutral" icon="warning" title={problem.title}>
          {problem.text}
        </Notice>
      )}
    </>
  );
  const targetBlock = (
    <DrawTarget
      target={target}
      newKey={newKey}
      listing={listing}
      folder={folder}
      typed={typed}
      onUseInNew={onUseInNew}
    >
      {!editing && <AgentRows agent={agent} picks="svg" methods={methods} />}
    </DrawTarget>
  );
  const pasted = (event: ClipboardEvent) => {
    const files = imageFiles(event.clipboardData);
    if (files.length > 0) {
      event.preventDefault();
      addFiles(key, files, Infinity);
    }
  };

  // A new drawing is asked for as an image model is; once the drawing is made, it is a conversation with its agent.
  if (!editing) {
    return (
      <div
        className="flex min-h-0 flex-1 flex-col"
        onPaste={pasted}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            void send();
          }
        }}
      >
        <div className="min-h-0 flex-1 overflow-y-auto">
          {targetBlock}
          <Section
            title="Prompt"
            open={open.prompt}
            onOpenChange={(prompt) => setOpen({ ...open, prompt })}
            aside={
              <PromptPicker
                editing={false}
                prompts={earlierPrompts(target, runs, listing)}
                current={draft.prompt}
                onPick={(prompt) => updateDraft(key, { prompt })}
              />
            }
          >
            <Textarea
              aria-label="Prompt"
              value={draft.prompt}
              onChange={(event) =>
                updateDraft(key, { prompt: event.target.value })
              }
              placeholder="Describe the drawing: subject, composition, style, and anything it must not have"
              className="block field-sizing-content max-h-80 min-h-19 resize-none"
            />
          </Section>
          <References
            open={open.references}
            onOpenChange={(shown) => setOpen({ ...open, references: shown })}
            target={key}
            references={references}
            room={Infinity}
            full={null}
            first={target.from ? 2 : 1}
            noun="reference"
            listing={listing}
            source={image?.name ?? null}
            edited={edited}
            onError={setFailure}
          />
          <Section
            title="Budget"
            open={open.budget}
            onOpenChange={(budget) => setOpen({ ...open, budget })}
          >
            <div className="flex flex-col gap-2">
              <BudgetRows
                budgets={budgets}
                fixed={false}
                match={from && sizeOf(from)}
                timeout={options.timeout_seconds}
                onChange={changeBudgets}
              />
            </div>
          </Section>
        </div>
        <footer className="shrink-0 border-t border-line bg-panel">
          {notes && (
            <div className="flex flex-col gap-2 px-3 pt-2.5">{notes}</div>
          )}
          <div className="flex px-3 pt-2.5 pb-3">
            <span
              title={problem?.title ?? problem?.text}
              className="flex min-w-0 flex-1"
            >
              <Button
                variant="primary"
                size="lg"
                className="flex-1"
                disabled={problem !== null || sending}
                onClick={() => void send()}
              >
                {sending && <LoadingMark />}
                {sending ? "Starting" : "Generate"}
              </Button>
            </span>
          </div>
        </footer>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col" onPaste={pasted}>
      {targetBlock}
      <Thread
        image={image}
        runs={turn.runs}
        label={label}
        viewing={shown?.version?.id ?? null}
        onView={onView}
      />
      {running && run && (
        <LiveStrip
          since={activity.at(-1)?.started ?? run.started}
          current={currentCall(activity.at(-1))}
          stopping={stopping === run.id}
          onStop={() => void stop()}
        />
      )}
      <footer className="shrink-0 border-t border-line bg-panel p-3">
        {notes && <div className="mb-2.5 flex flex-col gap-2">{notes}</div>}
        <Composer
          label="Message to the drawing agent"
          placeholder={
            running
              ? "Steer the agent while it works"
              : `Describe a change to ${key}`
          }
          value={draft.prompt}
          onChange={(prompt) => updateDraft(key, { prompt })}
          marks={marks}
          references={references}
          onRemoveMark={(id) => removeMark(key, id)}
          onRemoveReference={(id) => removeReference(key, id)}
          onAttach={() => setPicking(true)}
          onFiles={(transfer) => addFiles(key, imageFiles(transfer), Infinity)}
          onSend={() => void send()}
          sending={sending}
          blocked={problem ? (problem.title ?? problem.text) : null}
          sendLabel={running ? "Send to the working agent" : "Send"}
        >
          <AgentPicker agent={agent} picks="svg" methods={methods} />
          <BudgetPicker
            key={key}
            budgets={budgets}
            fixed
            match={null}
            timeout={options.timeout_seconds}
            onChange={changeBudgets}
          />
          <Switch
            checked={session.continuing}
            onChange={(resume) => setResume(key, resume)}
            disabled={!session.continuable}
            title={session.hint}
          >
            Continue session
          </Switch>
        </Composer>
      </footer>
      <ReferenceLibrary
        open={picking}
        onOpenChange={setPicking}
        target={key}
        references={references}
        room={Infinity}
        full={null}
        listing={listing}
        source={image.name}
        edited={edited}
      />
    </div>
  );
}
