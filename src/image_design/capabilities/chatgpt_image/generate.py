"""Create or edit an image with the image generation built into Codex, on the ChatGPT plan Codex is signed in with."""

from datetime import UTC, datetime
from functools import partial
import json
import os
from pathlib import Path, PurePosixPath
from string import Template
import sys

from pydantic import BaseModel

from image_design.intelligence.interface import AgentRun, Intelligence, select_intelligence
from image_design.intelligence.schemas import AgentRequest
from image_design.schemas import (
    CHATGPT_IMAGE_MODEL,
    DEFAULT_CHATGPT_REASONING_EFFORT,
    DEFAULT_INTELLIGENCE_MODELS,
    ImageDesignError,
    ImageRequestImage,
    ImageRequestPreview,
    ImageRunRecord,
    Mark,
    ReasoningEffort,
)
from image_design.shared.images import calls, pictures
from image_design.shared.images import detach as detaching
from image_design.shared.images import marks as marking
from image_design.shared.images.requests import (
    Reference,
    claimed,
    edited_version,
    invalid,
    previewed_source,
    source,
    validated,
    write,
    write_references,
)
from image_design.shared.images.requests import references as sent_references
from image_design.shared.images.runs import DetachedRun, ImageRun, InProcessRun, RunOutput
from image_design.shared.images.store import StoredImage, directories, image_name, new_run_id

# What starts a detached run, given its request on stdin.
BACKGROUND_COMMAND = [sys.executable, "-m", "image_design.capabilities.chatgpt_image.background"]
# What the agent is asked. It passes the image prompt to the image tool as written.
REQUEST = Template((Path(__file__).parent / "request.md").read_text(encoding="utf-8"))
# The most images the image tool takes, from codex-rs/ext/image-generation/src/tool.rs in
# https://github.com/openai/codex.
MAX_INPUT_IMAGES = 5
# The run's own timeout stops the agent. The agent's is a backstop, so it never ends the run first.
AGENT_GRACE_SECONDS = 60
# Where the agent's image is saved in the run's folder until it is kept as a version.
MADE = "made"
# What the image model is told about marks, which it receives drawn on a copy of the image, sent second.
MARKS_NOTE = (
    "Image 2 is image 1 with marks drawn on it, which show what this request refers to. Do not draw the marks in the "
    "image."
)


class ChatGPTImageRequest(BaseModel):
    """Everything `generate_chatgpt_image` was asked, which a detached run's process starts from."""

    prompt: str
    name: str
    directory: Path | None = None
    data_directory: Path | None = None
    references: list[Path] = []
    marks: list[Mark] = []
    version: str | None = None
    transparent: bool = False
    model: str | None = None
    reasoning_effort: ReasoningEffort = DEFAULT_CHATGPT_REASONING_EFFORT
    timeout_seconds: int = 600
    origin: str | None = None
    parent: str | None = None


async def generate_chatgpt_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    version: str | None = None,
    transparent: bool = False,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_CHATGPT_REASONING_EFFORT,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
    parent: str | None = None,
) -> ImageRun:
    """Start creating the image named `name`, or editing it when it exists, and return its run once it is sent."""
    request = validated(
        ChatGPTImageRequest,
        prompt=prompt,
        name=name,
        directory=directory,
        data_directory=data_directory,
        references=references or [],
        marks=marks or [],
        version=version,
        transparent=transparent,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        origin=origin,
        parent=parent,
    )
    if not detach:
        return await start(request, intelligence)
    if intelligence is not None:
        raise invalid(
            "An intelligence passed in cannot be used by a detached run, which runs in a process of its own. Leave out "
            "detach or the intelligence.",
            name,
        )
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    # Made absolute here, since the run's process need not resolve them from the same place.
    absolute = request.model_copy(
        update={
            "directory": root,
            "data_directory": data,
            "references": [path.resolve() for path in request.references],
        }
    )
    return await detaching.detach(BACKGROUND_COMMAND, absolute, root, data, DetachedRun)


def preview_chatgpt_image_request(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    version: str | None = None,
    transparent: bool = False,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_CHATGPT_REASONING_EFFORT,
) -> ImageRequestPreview:
    """What `generate_chatgpt_image` would send for these arguments, checked the same way, with nothing sent or kept.

    Whether Codex is installed and signed in with ChatGPT is not checked, since nothing is sent.
    """
    request = validated(
        ChatGPTImageRequest,
        prompt=prompt,
        name=name,
        directory=directory,
        data_directory=data_directory,
        references=references or [],
        marks=marks or [],
        version=version,
        transparent=transparent,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    image = image_name(request.name, root, data)
    sent_references(request.references)
    edited = previewed_source(root, data, image, request.version)
    sent = _plan(request, image, edited)
    images = [ImageRequestImage(role="source", path=edited)] if edited is not None else []
    if request.marks:
        images.append(ImageRequestImage(role="marked-copy", path=None))
    images.extend(ImageRequestImage(role="reference", path=path) for path in request.references)
    return ImageRequestPreview(
        method="chatgpt",
        name=image,
        edits=edited is not None,
        prompt=sent,
        added=sent[len(request.prompt) :].strip() or None,
        images=images,
        parameters={
            "transparent_background": request.transparent,
            "codex_model": request.model or DEFAULT_INTELLIGENCE_MODELS["codex"],
            "reasoning_effort": request.reasoning_effort,
        },
    )


async def start(request: ChatGPTImageRequest, intelligence: Intelligence | None = None) -> InProcessRun:
    """Check the request, keep what it sends, and start the agent that sends it."""
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    name = image_name(request.name, root, data)
    parent = calls.parent_of(root, data, request.parent, name)
    calls.require_given(parent, CHATGPT_IMAGE_MODEL, name)
    sent = sent_references(request.references)
    intelligence, model = select_intelligence(intelligence, "codex", request.model, DEFAULT_INTELLIGENCE_MODELS)
    run_id = new_run_id()
    with claimed(root, data, name, run_id) as (image, lock):
        folder = image.run_folder(run_id)
        images, prompt = _prepare(request, sent, image, folder / "inputs")
        version = edited_version(image, request.version)
        agent = await intelligence.start(
            AgentRequest(
                prompt=REQUEST.substitute(
                    prompt=prompt,
                    paths=json.dumps([str(path) for path in images]),
                    transparent=json.dumps(request.transparent),
                ),
                model=model,
                reasoning_effort=request.reasoning_effort,
                timeout_seconds=request.timeout_seconds + AGENT_GRACE_SECONDS,
                generated_images=folder / MADE,
            )
        )
        try:
            run = ImageRunRecord(
                id=run_id,
                method="chatgpt",
                prompt=request.prompt,
                request={
                    "codex_model": model,
                    "reasoning_effort": request.reasoning_effort,
                    "transparent": request.transparent,
                    "images": [path.relative_to(folder).as_posix() for path in images],
                    **({"version": version} if version else {}),
                },
                origin=request.origin,
                pid=os.getpid(),
                started=datetime.now(UTC),
            )
            calls.record(run, parent, image)
            image.runs.append(run)
            image.save_runs()
            work = partial(_follow, agent, run)
            return InProcessRun(image, run, work, request.timeout_seconds, lock, ".png", stop=agent.cancel)
        except BaseException:
            await agent.cancel()
            raise


def _plan(request: ChatGPTImageRequest, name: str, edited: Path | None) -> str:
    """The prompt to send to edit the file `edited`, or to create the image when there is none, once it is known the
    image tool can take the request."""
    if edited is None and request.marks:
        raise invalid(
            f"There is no image named {name} to edit, so marks cannot be used. Leave them out to create the "
            "image, or name an image that exists.",
            name,
        )
    if len(request.references) + (edited is not None) + bool(request.marks) > MAX_INPUT_IMAGES:
        raise invalid(
            f"A request can send at most {MAX_INPUT_IMAGES} images, counting the image being edited and, with marks, "
            "its marked copy. Send fewer references.",
            name,
        )
    marking.require_marks(request.marks)
    if edited is None:
        return request.prompt
    pictures.read(edited)
    if not request.marks:
        return request.prompt
    return f"{request.prompt}\n\n{MARKS_NOTE}\n{marking.describe(request.marks)}"


def _prepare(
    request: ChatGPTImageRequest, references: list[Reference], image: StoredImage, inputs: Path
) -> tuple[list[Path], str]:
    """The images to send, written into `inputs`, in the order the image tool gets them, and the prompt to send.

    The order is the image being edited, its marked copy, then the references.
    """
    edited = source(image, request.version)
    prompt = _plan(request, image.name, edited)
    inputs.mkdir(parents=True, exist_ok=True)
    sent: list[Path] = []
    if edited is not None:
        original = pictures.frame_png(edited)
        sent.append(write(inputs / "image.png", original))
        if request.marks:
            sent.append(write(inputs / "marked.png", marking.drawn(original, request.marks)))
    sent.extend(write_references(references, inputs))
    return sent, prompt


async def _follow(agent: AgentRun, run: ImageRunRecord, output: RunOutput) -> None:
    """Keep the first image the agent makes. The run stops the agent as this returns, so a run makes one image."""
    failure: str | None = None
    async for event in agent.events():
        if event.kind == "image":
            made = Path(event.data["path"])
            run.image_prompt = event.data.get("prompt")
            output.image(_png(made))
            made.unlink(missing_ok=True)
            return
        if event.kind == "tool_result" and event.data.get("success") is False:
            failure = event.data.get("error")
    ended = await agent.result()
    said = f" Codex said: {ended.text}" if ended.text else ""
    raise ImageDesignError(
        failure or ended.error or f"Codex ended without making an image.{said} Try again, or change the prompt.",
        "no-image",
    )


def _require_arguments(request: ChatGPTImageRequest) -> None:
    """Raise for arguments the image tool cannot take, before anything is kept or sent."""
    name = request.name
    if not request.prompt.strip():
        raise invalid("The prompt is empty. Say what to make, or what to change.", name)
    if request.timeout_seconds <= 0:
        raise invalid("timeout_seconds must be more than 0.", name)
    if PurePosixPath(name.replace("\\", "/")).suffix.lower() != ".png":
        raise invalid(
            "ChatGPT makes only PNG images, so the name must end in .png. Use generate_openai_image for other formats.",
            name,
        )


def _png(path: Path) -> bytes:
    """The image at `path` as a PNG."""
    content = path.read_bytes()
    picture = pictures.describe(content)
    return pictures.frame_png(path) if picture is not None and picture.format != "PNG" else content
