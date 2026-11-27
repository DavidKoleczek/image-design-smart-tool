import { useMemo, useState, type ClipboardEvent } from "react";

import { AgentPicker, AgentRows } from "@/components/activity/AgentPicker";
import { CallCard } from "@/components/activity/CallCard";
import { CallDialog } from "@/components/activity/CallDialog";
import { Composer } from "@/components/activity/Composer";
import { LiveStrip } from "@/components/activity/RunParts";
import { Thread } from "@/components/activity/Thread";
import {
  ImageModelPicker,
  ImageModelSelect,
} from "@/components/ImageModelPicker";
import { NewImageName } from "@/components/NewImageName";
import { PromptPicker } from "@/components/PromptPicker";
import { ReferenceLibrary } from "@/components/ReferenceLibrary";
import { References } from "@/components/References";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { FormRow } from "@/components/ui/form-row";
import { LoadingMark } from "@/components/ui/loading-mark";
import { Notice } from "@/components/ui/notice";
import { Section } from "@/components/ui/section";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  cancelImage,
  designImage,
  steerImage,
  type AppDesignRequest,
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
import { fillEditor } from "@/lib/design";
import { draftOf, dropDraft, updateDraft, useDraft } from "@/lib/drafts";
import { agentOf } from "@/lib/drawing";
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
  uploadMask,
  useReferences,
} from "@/lib/references";
import {
  CHATGPT,
  extensionOf,
  folderIn,
  freeNewName,
  designModel,
  imageModelLabel,
  qualityLabel,
  SIZES,
  stem,
  typedName,
  type Problem,
} from "@/lib/request";
import type { Runs } from "@/lib/runs";
import { sessionOf, setResume, useResume } from "@/lib/sessions";
import type { Sheet } from "@/lib/sheets";
import { flushAppState, updateAppState, useAppState } from "@/lib/state";
import { openImage } from "@/lib/tabs";
import {
  conversationOf,
  currentCall,
  sentTurn,
  useSentTurn,
  type ImageCall,
} from "@/lib/thread";
import type { Shown } from "@/lib/viewed";

// In the size and quality lists, what leaves the choice to the agent.
const AGENT_CHOICE = "agent";

function updateDesign(change: Partial<AppDesignRequest>) {
  updateAppState((current) => ({
    ...current,
    design: { ...current.design, ...change },
  }));
}

function pickImageModel(image_model: string | null) {
  updateDesign({ image_model });
}

/** The size and quality picked for a new image, of those offered; none with ChatGPT, which chooses its own. */
function outputOf(
  design: AppDesignRequest,
  methods: ImageMethods,
  imageModel: string,
): { size: [number, number] | null; quality: string | null } {
  if (imageModel === CHATGPT) {
    return { size: null, quality: null };
  }
  return {
    size:
      SIZES.find((each) => each.size.join("x") === design.size?.join("x"))
        ?.size ?? null,
    quality:
      design.quality !== null &&
      design.quality !== "auto" &&
      methods.openai.qualities.includes(design.quality)
        ? design.quality
        : null,
  };
}

/** The size and quality a new image is made at, which the agent is told to pass to its calls. */
function OutputRows({
  methods,
  imageModel,
}: {
  methods: ImageMethods;
  imageModel: string;
}) {
  const { state } = useAppState();
  const output = outputOf(state.design, methods, imageModel);
  const byChatGPT = imageModel === CHATGPT ? "Chosen by ChatGPT" : undefined;
  return (
    <>
      <FormRow label="Size" off={byChatGPT}>
        <Select
          label="Size"
          value={output.size?.join("x") ?? AGENT_CHOICE}
          disabled={byChatGPT !== undefined}
          onChange={(picked) =>
            updateDesign({
              size:
                SIZES.find((each) => each.size.join("x") === picked)?.size ??
                null,
            })
          }
          items={[
            { value: AGENT_CHOICE, label: "Agent's choice" },
            ...SIZES.map((each) => ({
              value: each.size.join("x"),
              label: each.label,
              aside: dimensions(...each.size),
            })),
          ]}
        />
      </FormRow>
      <FormRow label="Quality" off={byChatGPT}>
        <Select
          label="Quality"
          value={output.quality ?? AGENT_CHOICE}
          disabled={byChatGPT !== undefined}
          onChange={(picked) =>
            updateDesign({ quality: picked === AGENT_CHOICE ? null : picked })
          }
          items={[
            { value: AGENT_CHOICE, label: "Agent's choice" },
            ...methods.openai.qualities
              .filter((quality) => quality !== "auto")
              .map((quality) => ({
                value: quality,
                label: qualityLabel(quality),
              })),
          ]}
        />
      </FormRow>
    </>
  );
}

/** Why the message cannot be sent as it stands; null when it can. */
function problemOf(
  name: string | null,
  message: string,
  methods: ImageMethods,
  imageModel: string,
  listing: ImageListing | null,
  references: { name: string; state: string }[],
  steering: boolean,
  creates: boolean,
): Problem | null {
  // A server that has an agent for images says of each image how its last run went, if only that it had none.
  if (
    listing !== null &&
    listing.images.length > 0 &&
    listing.images.every((image) => image.design === undefined)
  ) {
    return {
      title: "This server has no agent for images.",
      text: "Write the image call yourself, with Write image call at the top of the pane.",
      quiet: false,
    };
  }
  if (!steering && !methods.design.ready) {
    return {
      title: "The agent is not set up where the app runs.",
      text: methods.design.problem ?? "",
      quiet: false,
    };
  }
  const method = imageModel === CHATGPT ? methods.chatgpt : methods.openai;
  const label = imageModelLabel(imageModel, methods);
  if (!steering && !method.ready) {
    return {
      title: `${label} is not set up where the app runs.`,
      text: method.problem ?? "",
      quiet: false,
    };
  }
  if (
    !steering &&
    name !== null &&
    !method.formats.includes(extensionOf(name))
  ) {
    return {
      text: `${label} makes only ${method.formats.join(", ")} images, so it cannot change ${name}. Pick an OpenAI image model.`,
      quiet: false,
    };
  }
  if (creates) {
    if (name === null) {
      return { text: "Give the image a name.", quiet: true };
    }
    const typed = typedProblem(stem(name), extensionOf(name));
    if (typed) {
      return { text: typed, quiet: false };
    }
    const wanted = name.toLowerCase();
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
        text: creates ? "Describe the image." : "Write a message.",
        quiet: true,
      }
    : null;
}

/**
 * Creating and editing an image through an agent. A new image is asked for with a form, as a new drawing is; one
 * already made is a conversation that stays with it: what was asked, what the agent said and did, each image call
 * that was made, and a message box that starts the agent or, while it works, steers it. An image call opens in full,
 * and opens in the editor to be changed.
 */
export function ImagePane({
  methods,
  listing,
  image,
  shown,
  runs,
  mode,
  newKey,
  onCreated,
  onChanged,
  onView,
  onSheet,
}: {
  methods: ImageMethods;
  listing: ImageListing | null;
  /** The image in view; none for a new image. */
  image: ImageSummary | null;
  shown: Shown | null;
  runs: Runs;
  mode: CanvasMode | null;
  /** What a new image's message is kept under. */
  newKey: string;
  onCreated: (name: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onView: (version: string | null) => void;
  /** Open the editor of an image call over the pane. */
  onSheet: (sheet: Sheet) => void;
}) {
  const { state } = useAppState();
  const key = image ? image.name : newKey;
  const draft = useDraft(key);
  const references = useReferences(key);
  const guides = useGuides(key, shown?.picture?.key ?? null);
  const { numbered } = useCanvas();
  const frame = useSourceFrame(image, shown, mode);
  const resume = useResume(key);
  const [opened, setOpened] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [open, setOpen] = useState({ prompt: true, references: true });

  const agent = agentOf(state.design, methods.design);
  const imageModel = designModel(
    state.design.image_model,
    methods,
    image?.name ?? null,
  );
  // Left to the order in Settings until the person picks a model, and again once they pick Default.
  const byDefault = {
    picked: state.design.image_model === null,
    onPick: () => pickImageModel(null),
  };
  const conversation = useMemo(
    () => (image ? conversationOf(image, runs) : []),
    [image, runs],
  );
  const turn = useSentTurn(key, conversation);
  const calls = conversation.flatMap((run) =>
    run.blocks.flatMap((block) => (block.kind === "call" ? [block.call] : [])),
  );
  const designing = image?.design?.status === "running";
  const working = designing || image?.status === "running";
  const lastAgent = conversation.findLast((run) => run.kind === "agent");
  const lastRun = conversation.at(-1);
  const ranOn = lastAgent?.request.agent_provider;
  const session = sessionOf(
    typeof ranOn === "string" ? ranOn : null,
    agent.provider,
    resume,
    "the image's history",
  );
  const format =
    imageModel === CHATGPT ? methods.chatgpt.formats[0] : state.request.format;
  const folder = folderIn(listing, draft.folder);
  const typed = draft.name ?? freeNewName(listing, format, folder);
  const bare = typedName(typed, folder);
  const name = image ? image.name : bare === "" ? null : `${bare}${format}`;
  const marks = image && mode === "markup" ? guides.marks : [];
  const edited = shown && !shown.file ? (shown.version?.id ?? null) : null;
  const problem = problemOf(
    name,
    draft.message,
    methods,
    imageModel,
    listing,
    references,
    designing,
    image === null,
  );
  const agentLabel = (model: string) =>
    methods.design.models.find((each) => each.id === model)?.label ?? model;
  const modelLabel = (model: string) => imageModelLabel(model, methods);

  const send = async () => {
    if (problem !== null || sending || name === null) {
      return;
    }
    setSending(true);
    setFailure(null);
    const message = draft.message;
    const output = outputOf(state.design, methods, imageModel);
    const sent = sentReferences(references);
    const sentMarks = marks.map((mark) => sentMark(mark, numbered));
    // A turn on the image shows in the thread at once, and the message leaves the box, while its run starts.
    const starts = image !== null && !designing;
    if (starts) {
      turn.send(
        sentTurn(
          conversation,
          message,
          sentMarks,
          {
            model: agent.model,
            reasoning_effort: agent.effort,
            resumed: session.continuing,
          },
          "agent",
        ),
      );
      updateDraft(key, { message: "" });
    }
    try {
      // The server sends only references it knows the app offers, a pin among them once the pin is saved.
      await flushAppState();
      if (designing && image) {
        await steerImage({
          name,
          message,
          ...(sent.length > 0 ? { references: sent } : {}),
          ...(sentMarks.length > 0 ? { marks: sentMarks } : {}),
        });
        clearMarks(image.name);
        updateDraft(key, { message: "" });
      } else {
        const mask =
          image &&
          mode === "mask" &&
          guides.painted > 0 &&
          shown &&
          shown.width !== null &&
          shown.height !== null
            ? await uploadMask(image.name, shown.width, shown.height)
            : null;
        const started = await designImage({
          prompt: message,
          name,
          ...(sent.length > 0 ? { references: sent } : {}),
          ...(sentMarks.length > 0 ? { marks: sentMarks } : {}),
          ...(mask ? { mask: mask.upload } : {}),
          ...(image && edited ? { version: edited } : {}),
          ...(image && frame !== null ? { frame } : {}),
          resume_session: session.continuing,
          image_model: imageModel,
          // Picked for a new image, as where it starts.
          ...(!image && output.size ? { size: output.size } : {}),
          ...(!image && output.quality ? { quality: output.quality } : {}),
          agent_provider: agent.provider,
          model: agent.model,
          reasoning_effort: agent.effort,
        });
        if (image) {
          turn.started(started.run_id);
          clearGuides(image.name);
          // What the agent makes lands in the image's file, so that is what shows while it works.
          onView(null);
          await onChanged();
        } else {
          await onCreated(started.name);
          dropDraft(key);
        }
      }
      clearReferences(key);
    } catch (cause) {
      if (starts) {
        turn.failed();
        // The message goes back in the box, unless another was written there meanwhile.
        if (draftOf(key).message === "") {
          updateDraft(key, { message });
        }
      }
      setFailure(
        `${designing ? "The message did not reach the agent." : "The agent did not start."} ${describe(cause)}`,
      );
    } finally {
      setSending(false);
    }
  };

  const stop = async () => {
    if (!image) {
      return;
    }
    setStopping(true);
    setFailure(null);
    try {
      await cancelImage(image.name);
    } catch (cause) {
      setFailure(`Could not stop it. ${describe(cause)}`);
    } finally {
      setStopping(false);
    }
  };

  const edit = (call: ImageCall) => {
    fillEditor(key, call, methods);
    setOpened(null);
    onSheet({ title: "Image call", filled: true });
  };

  const pasted = (event: ClipboardEvent) => {
    const files = imageFiles(event.clipboardData);
    if (files.length > 0) {
      event.preventDefault();
      addFiles(key, files, Infinity);
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

  // A new image is asked for as a new drawing is; once it is made, it is a conversation with its agent.
  if (!image) {
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
          <div className="flex shrink-0 flex-col gap-2 border-b border-line p-3">
            <div className="flex items-center gap-2.5">
              <NewImageName
                draftKey={newKey}
                listing={listing}
                folder={folder}
                typed={typed}
                extension={format}
              />
            </div>
            <AgentRows agent={agent} picks="design" methods={methods} />
            <FormRow label="Image model">
              <ImageModelSelect
                value={imageModel}
                onChange={pickImageModel}
                methods={methods}
                byDefault={byDefault}
              />
            </FormRow>
            <OutputRows methods={methods} imageModel={imageModel} />
          </div>
          <Section
            title="Prompt"
            open={open.prompt}
            onOpenChange={(prompt) => setOpen({ ...open, prompt })}
            aside={
              <PromptPicker
                editing={false}
                prompts={earlierPrompts(
                  { image: null, name: bare, from: null },
                  runs,
                  listing,
                )}
                current={draft.message}
                onPick={(message) => updateDraft(key, { message })}
              />
            }
          >
            <Textarea
              aria-label="Prompt"
              value={draft.message}
              onChange={(event) =>
                updateDraft(key, { message: event.target.value })
              }
              placeholder="Describe the image: subject, composition, style, and anything it must not have"
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
            first={1}
            noun="reference"
            listing={listing}
            source={null}
            edited={null}
            onError={setFailure}
          />
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
      <Thread
        image={image}
        runs={turn.runs}
        label={agentLabel}
        viewing={shown?.version?.id ?? null}
        onView={onView}
        renderCall={(call) => (
          <CallCard
            call={call}
            here={call.name === image.name}
            label={modelLabel}
            onOpen={() => setOpened(call.id)}
            onOpenImage={() => openImage(call.name, "keep")}
          />
        )}
        images={listing?.images}
        onOpenVersion={(name, version) => openImage(name, "keep", version)}
      />
      {working && lastRun && (
        <LiveStrip
          since={(designing ? lastAgent : lastRun)?.started ?? lastRun.started}
          current={designing ? currentCall(lastAgent) : null}
          stopping={stopping}
          onStop={() => void stop()}
        />
      )}
      <footer className="shrink-0 border-t border-line bg-panel p-3">
        {notes && <div className="mb-2.5 flex flex-col gap-2">{notes}</div>}
        <Composer
          label="Message to the agent"
          placeholder={
            designing
              ? "Steer the agent while it works"
              : `Describe a change to ${image.name}`
          }
          value={draft.message}
          onChange={(message) => updateDraft(key, { message })}
          marks={marks}
          references={references}
          onRemoveMark={(id) => removeMark(key, id)}
          onRemoveReference={(id) => removeReference(key, id)}
          onAttach={() => setPicking(true)}
          onFiles={(transfer) => addFiles(key, imageFiles(transfer), Infinity)}
          onSend={() => void send()}
          sending={sending}
          blocked={problem ? (problem.title ?? problem.text) : null}
          sendLabel={designing ? "Send to the working agent" : "Send"}
        >
          <AgentPicker agent={agent} picks="design" methods={methods} />
          <ImageModelPicker
            value={imageModel}
            onChange={pickImageModel}
            methods={methods}
            byDefault={byDefault}
          />
          <Switch
            checked={session.continuing}
            onChange={(next) => setResume(key, next)}
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
      <CallDialog
        call={calls.find((call) => call.id === opened) ?? null}
        label={modelLabel}
        onClose={() => setOpened(null)}
        onEdit={edit}
      />
    </div>
  );
}
