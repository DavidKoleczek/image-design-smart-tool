"""Create or edit an image with an agent that directs the image models: it writes each image call and makes it with
the tool's own commands.

The agent's run is kept with the image in designs.json and claims the image's conversation, not the image: the calls
it makes each claim the image only while they run, as any call does. One agent at a time works on a conversation.
"""

import asyncio
import contextlib
from datetime import UTC, datetime
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
from typing import NamedTuple

from pydantic import BaseModel

from image_design.capabilities.design_image import prompting, told, tooling
from image_design.capabilities.design_image.runs import DesignDetachedRun, DesignInProcessRun, DesignRun
from image_design.intelligence.interface import AgentRun, Intelligence, resolve_agent_provider, select_intelligence
from image_design.intelligence.schemas import AgentRequest, HostWorkspace, Steering
from image_design.schemas import (
    CHATGPT_IMAGE_MODEL,
    DEFAULT_INTELLIGENCE_MODELS,
    DEFAULT_REASONING_EFFORT,
    IMAGE_FORMATS,
    SVG_SUFFIX,
    AgentProvider,
    ImageDesignError,
    ImageRunRecord,
    Mark,
    OpenAIImageQuality,
    ReasoningEffort,
)
from image_design.shared.images import agent_events, calls, pictures, sessions, steering
from image_design.shared.images import detach as detaching
from image_design.shared.images import marks as marking
from image_design.shared.images import runs as image_runs
from image_design.shared.images.requests import Reference, invalid, references, validated, write, write_references
from image_design.shared.images.runs import CANCEL, RunOutput
from image_design.shared.images.store import (
    CRASHED,
    SESSIONS,
    StoredImage,
    directories,
    find_image,
    image_by_id,
    image_name,
    new_image,
    new_run_id,
    release_lock,
    take_lock,
)

# What starts a detached run, given its request on stdin.
BACKGROUND_COMMAND = [sys.executable, "-m", "image_design.capabilities.design_image.background"]
# The run's own timeout stops the agent. The agent's is a backstop, so it never ends the run first.
AGENT_GRACE_SECONDS = 60
INPUTS = "inputs"
SHOWN = "shown"
MARKS = "marks.json"
MARKED = "marked.png"
MASK = "mask.png"
# Where the agent writes the files it makes for an image, such as scripts and composites, in the image's folder.
WORK = "work"
# The longest side of an image shown to the agent, which agent providers take inline; the files it is told of are
# full size.
SHOWN_EDGE = 1568
# What one agent at a time claims of an image: its conversation, by the image's id, which stays the same as it moves.
CONVERSATION = "conversation-{id}"


class DesignImageRequest(BaseModel):
    """Everything `design_image` was asked, which a detached run's process starts from."""

    prompt: str
    name: str
    image_model: str
    size: tuple[int, int] | None = None
    quality: OpenAIImageQuality | None = None
    directory: Path | None = None
    data_directory: Path | None = None
    references: list[Path] = []
    marks: list[Mark] = []
    mask: Path | None = None
    version: str | None = None
    frame: int | None = None
    resume_session: bool | str = False
    agent_provider: AgentProvider | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT
    timeout_seconds: int | None = None
    origin: str | None = None


async def design_image(
    prompt: str,
    name: str,
    image_model: str,
    size: tuple[int, int] | None = None,
    quality: OpenAIImageQuality | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    mask: Path | None = None,
    version: str | None = None,
    frame: int | None = None,
    resume_session: bool | str = False,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int | None = None,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> DesignRun:
    """Start the image's agent on a request, and return its run once it is kept. `image_model` is what it makes its
    images with, once known to be set up."""
    request = validated(
        DesignImageRequest,
        prompt=prompt,
        name=name,
        image_model=image_model,
        size=size,
        quality=quality,
        directory=directory,
        data_directory=data_directory,
        references=references or [],
        marks=marks or [],
        mask=mask,
        version=version,
        frame=frame,
        resume_session=resume_session,
        agent_provider=agent_provider,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        origin=origin,
    )
    return await begin(request, detach, intelligence)


async def begin(request: DesignImageRequest, detach: bool, intelligence: Intelligence | None) -> DesignRun:
    """Start the run here, or in a process of its own when `detach`."""
    if not detach:
        return await start(request, intelligence)
    if intelligence is not None:
        raise invalid(
            "An intelligence passed in cannot be used by a detached run, which runs in a process of its own. Leave out "
            "detach or the intelligence.",
            request.name,
        )
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    # Made absolute here, since the run's process need not resolve them from the same place.
    absolute = request.model_copy(
        update={
            "directory": root,
            "data_directory": data,
            "references": [path.resolve() for path in request.references],
            "mask": request.mask.resolve() if request.mask is not None else None,
        }
    )
    return await detaching.detach(BACKGROUND_COMMAND, absolute, root, data, DesignDetachedRun)


class Context(NamedTuple):
    """What the agent's work goes on with once its run is kept."""

    request: DesignImageRequest
    image: StoredImage
    run: ImageRunRecord
    intelligence: Intelligence
    model: str
    resumed: ImageRunRecord | None
    looking_at: Path | None
    version: str | None
    shown: list[Path]
    given: list[str]


async def start(request: DesignImageRequest, intelligence: Intelligence | None = None) -> DesignInProcessRun:
    """Check the request, claim the image's conversation, keep the run, and start the work that runs the agent."""
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    name = image_name(request.name, root, data)
    sent = references(request.references)
    marking.require_marks(request.marks)
    run_id = new_run_id()
    image, claim = _claimed(root, data, name, run_id)
    folder = image.run_folder(run_id)
    try:
        _end_crashed(image)
        resumed = sessions.resumed(image.designs, request.resume_session, image.name)
        provider = sessions.provider(request.agent_provider, resumed, image.name)
        if intelligence is None:
            provider = resolve_agent_provider(provider)
        intelligence, model = select_intelligence(intelligence, provider, request.model, DEFAULT_INTELLIGENCE_MODELS)
        version, looking_at = _looking_at(image, request)
        shown, given, recorded = _prepare(request, sent, image, looking_at, folder)
        session = _session(image, resumed, run_id)
        told_calls = told.history(image) if resumed is None else told.since(image, session)
        run = ImageRunRecord(
            id=run_id,
            method="design",
            prompt=request.prompt,
            request={
                "model": model,
                "reasoning_effort": request.reasoning_effort,
                "agent_provider": provider,
                "image_model": request.image_model,
                "size": request.size,
                "quality": request.quality,
                "timeout_seconds": request.timeout_seconds,
                "resumed": resumed.session_id if resumed is not None else None,
                "since": [call.run.id for call in told_calls] if resumed is not None else [],
                "history": [call.run.id for call in told_calls] if resumed is None else [],
                "told": told.told(told_calls),
                "version": version,
                "frame": request.frame,
                **recorded,
            },
            origin=request.origin,
            agent_provider=provider,
            session_id=resumed.session_id if resumed is not None else None,
            pid=os.getpid(),
            started=datetime.now(UTC),
        )
        image.designs.append(run)
        image.save_designs()
        context = Context(request, image, run, intelligence, model, resumed, looking_at, version, shown, given)
        suffix = PurePosixPath(image.name).suffix.lower()
        return DesignInProcessRun(
            image, run, lambda output: _work(context, output), request.timeout_seconds, claim, suffix
        )
    except BaseException:
        release_lock(claim, run_id)
        shutil.rmtree(folder, ignore_errors=True)
        if not image.versions.versions and not image.runs and not image.designs:
            shutil.rmtree(image.folder, ignore_errors=True)
        raise


def _claimed(root: Path, data: Path, name: str, run_id: str) -> tuple[StoredImage, Path]:
    """The image named `name`, kept from now on when it is new, and this run's claim on its conversation."""
    image = find_image(root, data, name)
    if image is None:
        # Claimed as a call claims it while it is made, so two requests at once cannot both make it.
        holder = f"design-{run_id}"
        lock = take_lock(data, name, holder)
        try:
            image = find_image(root, data, name) or new_image(root, data, name)
        finally:
            release_lock(lock, holder)
    try:
        claim = take_lock(data, CONVERSATION.format(id=image.record.id), run_id)
    except ImageDesignError as error:
        if error.reason != "already-running":
            raise
        raise ImageDesignError(
            f"An agent is already working on {image.name}. Send it a message with steer_image, or stop it with "
            "cancel_image and start again.",
            "already-running",
            image.name,
        ) from None
    # Read again with the claim held, so the runs of an agent that just ended are there.
    return image_by_id(root, data, image.record.id) or image, claim


def _end_crashed(image: StoredImage) -> None:
    """Mark the agent's run whose process ended without ending it, which the claim just taken shows it did."""
    last = image.designs[-1] if image.designs else None
    if last is not None and last.status == "running":
        last.status = "failed"
        last.error = CRASHED
        image.save_designs()


def _session(image: StoredImage, resumed: ImageRunRecord | None, run_id: str) -> list[ImageRunRecord]:
    """The turns of the session the run `run_id` goes on in, oldest first, before that run."""
    if resumed is None:
        return []
    return [run for run in image.designs if run.session_id == resumed.session_id and run.id != run_id]


def _looking_at(image: StoredImage, request: DesignImageRequest) -> tuple[str | None, Path | None]:
    """The version the request is about and its file, once what goes with it is known to fit; None for both when the
    image has no file to show, so the request creates it."""
    if request.version is not None:
        return request.version, image.folder / image.version(request.version).file
    if image.path.is_file():
        return (image.versions.current if image.current_file_matches() else None), image.path
    for what, used in (("marks", bool(request.marks)), ("a mask", request.mask is not None)):
        if used:
            raise invalid(
                f"There is no image named {image.name} to edit, so {what} cannot go with the request. Leave them "
                "out to create the image, or name an image that exists.",
                image.name,
            )
    if request.frame is not None:
        raise invalid(f"There is no image named {image.name}, so it has no frame {request.frame}.", image.name)
    return None, None


def _prepare(
    request: DesignImageRequest, sent: list[Reference], image: StoredImage, looking_at: Path | None, folder: Path
) -> tuple[list[Path], list[str], dict[str, object]]:
    """Write what goes with the request into the run's folder; return the images to show the agent, what it is told
    of them, and what the run's record keeps of them."""
    inputs = folder / INPUTS
    shown_folder = inputs / SHOWN
    shown_folder.mkdir(parents=True, exist_ok=True)
    shown: list[Path] = []
    marked = marks_file = mask = None
    if looking_at is not None:
        frame = request.frame or 0
        view = write(shown_folder / "image.png", pictures.fitted_png(looking_at, SHOWN_EDGE, frame))
        shown.append(view)
        if request.marks:
            marked = write(inputs / MARKED, marking.drawn(view.read_bytes(), request.marks))
            shown.append(marked)
            marks_file = inputs / MARKS
            marks_file.write_text(
                json.dumps([mark.model_dump(mode="json") for mark in request.marks], indent=2), encoding="utf-8"
            )
        if request.mask is not None:
            mask = write(inputs / MASK, pictures.png(request.mask))
    given = write_references(sent, inputs)
    for number, path in enumerate(given, 1):
        shown.append(write(shown_folder / f"{number}.png", pictures.fitted_png(path, SHOWN_EDGE)))
    recorded: dict[str, object] = {
        "images": [path.relative_to(folder).as_posix() for path in given],
        "marks": [mark.model_dump(mode="json") for mark in request.marks],
    }
    if mask is not None:
        recorded["mask"] = mask.relative_to(folder).as_posix()
    told_of = prompting.given(request.marks, marked, marks_file, mask, given)
    return shown, told_of + prompting.picked(request.size, request.quality), recorded


async def _work(context: Context, output: RunOutput) -> None:
    """Run the agent on the request and report what it does."""
    request, run = context.request, context.run
    image = image_by_id(context.image.root, context.image.data, context.image.record.id) or context.image
    session = _session(image, context.resumed, run.id)
    told_calls = told.history(image) if context.resumed is None else told.since(image, session)
    run.request["told"] = told.told(told_calls)
    (image.folder / WORK).mkdir(parents=True, exist_ok=True)
    agent = await context.intelligence.start(
        AgentRequest(
            prompt=_prompt(context, image, session, told_calls),
            model=context.model,
            images=context.shown,
            workspace=HostWorkspace(path=Path.cwd()),
            writable=True,
            reasoning_effort=request.reasoning_effort,
            timeout_seconds=(
                None if request.timeout_seconds is None else request.timeout_seconds + AGENT_GRACE_SECONDS
            ),
            resume=context.resumed.session_id if context.resumed is not None else None,
            session_directory=image.folder / SESSIONS,
            skill_directories=tooling.skill_directories(),
            path_directories=[tooling.command_directory()],
            environment={calls.PARENT: run.id},
        )
    )
    run.session_id = agent.session_id or run.session_id
    delivering = asyncio.create_task(_deliver(agent, context.intelligence.steering, image, run, output))
    try:
        async for event in agent.events():
            if agent.session_id is not None:
                run.session_id = agent.session_id
            if event.kind == "terminal":
                continue
            output.event("agent", agent_events.shown(event), event.model_dump(mode="json"))
            if event.kind == "usage":
                output.used(agent_events.added(run.usage, event.data))
    except asyncio.CancelledError:
        _stop_calls(image, run)
        raise
    finally:
        delivering.cancel()
        await asyncio.wait([delivering])
        await agent.cancel()
    ended = await agent.result()
    if ended.error is not None or ended.cancelled:
        stopped = ended.error or "it was stopped."
        raise ImageDesignError(
            f"The agent did not finish: {stopped} What it made is kept; go on with resume_session=True.",
            "agent-failed",
            image.name,
        )


def _prompt(context: Context, image: StoredImage, session: list[ImageRunRecord], told_calls: list[told.Call]) -> str:
    request = context.request
    resumed = context.resumed
    target = prompting.target(
        image.name, image.path, told.state(image), context.version, context.looking_at, request.frame
    )
    told_block = told.describe(told_calls, image, session, new=resumed is None)
    if resumed is None:
        # What the agent's commands default to, from the working directory it is started in.
        default_root, default_data = directories(None, None)
        return prompting.new(
            request.prompt,
            target,
            context.given,
            image.folder / WORK,
            prompting.directories(image.root, image.data, default_root, default_data),
            request.image_model,
            context.looking_at is not None,
            told_block,
        )
    switched = not session or session[-1].request.get("image_model") != request.image_model
    return prompting.resume(request.prompt, target, context.given, request.image_model, switched, told_block)


def _stop_calls(image: StoredImage, run: ImageRunRecord) -> None:
    """Ask every call the agent made that is still going to stop, as `cancel_image` does, since the agent stopped."""
    fresh = image_by_id(image.root, image.data, image.record.id) or image
    for call in told.calls_of(fresh):
        if call.run.parent == run.id and call.run.status == "running":
            with contextlib.suppress(OSError):
                (call.image.run_folder(call.run.id) / CANCEL).touch()


async def _deliver(
    agent: AgentRun, steering_mode: Steering, image: StoredImage, run: ImageRunRecord, output: RunOutput
) -> None:
    """Deliver each steering message left for the run, looking for them as often as for a cancel."""
    run_folder = image.run_folder(run.id)
    while True:
        for message in steering.pending(run_folder):
            await _deliver_one(agent, steering_mode, message, image, run_folder, output)
        await asyncio.sleep(image_runs.POLL_SECONDS)


async def _deliver_one(
    agent: AgentRun, steering_mode: Steering, message: Path, image: StoredImage, run_folder: Path, output: RunOutput
) -> None:
    given = steering.read(message)
    folder = steering.delivered(message, run_folder)
    attached = [folder / name for name in given.references]
    shown = list(attached)
    marked = marks_file = None
    if given.marks and image.path.is_file():
        marked = write(folder / MARKED, marking.drawn(pictures.fitted_png(image.path, SHOWN_EDGE), given.marks))
        shown.insert(0, marked)
        marks_file = folder / MARKS
        marks_file.write_text(
            json.dumps([mark.model_dump(mode="json") for mark in given.marks], indent=2), encoding="utf-8"
        )
    error: str | None = None
    try:
        told_of = prompting.given(given.marks, marked, marks_file, None, attached)
        await agent.steer(prompting.steered(given.message, told_of), shown)
    except ImageDesignError as failure:
        error = str(failure)
    output.event(
        "steered",
        f"Steered: {given.message}" if error is None else f"The steering message was not delivered: {error}",
        {
            "message": given.message,
            "origin": given.origin,
            "references": [str(path) for path in attached],
            "marks": [mark.model_dump(mode="json") for mark in given.marks],
            "steering": steering_mode,
            "error": error,
        },
    )


def _require_arguments(request: DesignImageRequest) -> None:
    """Raise for arguments the request cannot take, before anything is kept or started."""
    name = request.name
    suffix = PurePosixPath(name.replace("\\", "/")).suffix.lower()
    if suffix == SVG_SUFFIX:
        raise invalid(
            f"{name!r} is an SVG, which draw_svg_image's agent draws with code. Name an image ending in one of: "
            f"{', '.join(IMAGE_FORMATS)}, or draw the SVG with draw_svg_image.",
            name,
        )
    if not request.prompt.strip():
        raise invalid("The prompt is empty. Say what to make, or what to change.", name)
    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise invalid("timeout_seconds must be more than 0, or None for no limit.", name)
    if request.frame is not None and request.frame < 0:
        raise invalid(f"frame is {request.frame}. Frames count from 0.", name)
    if request.image_model == CHATGPT_IMAGE_MODEL and (request.size is not None or request.quality is not None):
        raise invalid(
            "ChatGPT chooses the size and quality itself. Leave them out, or give the agent an OpenAI image model.",
            name,
        )
    if request.size is not None and (problem := pictures.size_problem(*request.size, animated=suffix == ".gif")):
        raise invalid(f"The size {request.size[0]}x{request.size[1]} does not work: {problem}.", name)
