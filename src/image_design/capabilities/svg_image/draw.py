"""Create or edit an SVG image by running an agent that draws it with code: an image.py that writes the SVG."""

import asyncio
import contextlib
from datetime import UTC, datetime
from functools import partial
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

from pydantic import BaseModel

from image_design.capabilities.svg_image import build, measure, prompting
from image_design.capabilities.svg_image.runs import SvgDetachedRun, SvgInProcessRun, SvgRun
from image_design.intelligence.interface import AgentRun, Intelligence, resolve_agent_provider, select_intelligence
from image_design.intelligence.schemas import AgentRequest, HostWorkspace, Steering
from image_design.schemas import (
    DEFAULT_INTELLIGENCE_MODELS,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SVG_CANVAS,
    NOT_GIVEN,
    SVG_SUFFIX,
    AgentProvider,
    ImageDesignError,
    ImageRunRecord,
    Mark,
    NotGiven,
    ReasoningEffort,
    SvgBudgets,
)
from image_design.shared.images import agent_events, pictures, sessions, steering
from image_design.shared.images import detach as detaching
from image_design.shared.images import marks as marking
from image_design.shared.images import runs as image_runs
from image_design.shared.images.requests import (
    Reference,
    claimed,
    invalid,
    references,
    validated,
    write,
    write_references,
)
from image_design.shared.images.runs import RunOutput
from image_design.shared.images.store import (
    SCRIPT,
    SESSIONS,
    StoredImage,
    directories,
    image_name,
    lock_path,
    new_run_id,
    read_script,
)

# What starts a detached run, given its request on stdin.
BACKGROUND_COMMAND = [sys.executable, "-m", "image_design.capabilities.svg_image.background"]
# The run's own timeout stops the agent. The agent's is a backstop, so it never ends the run first.
AGENT_GRACE_SECONDS = 60
WORK = "work"
INPUTS = "inputs"
CURRENT_PNG = "current.png"
CURRENT_SVG = "current.svg"
MARKED = "marked.png"
BUDGETS = ("max_bytes",)


class SvgImageRequest(BaseModel):
    """Everything `draw_svg_image` was asked, which a detached run's process starts from."""

    prompt: str
    name: str
    directory: Path | None = None
    data_directory: Path | None = None
    references: list[Path] = []
    marks: list[Mark] = []
    canvas: tuple[int, int] | NotGiven = NOT_GIVEN
    max_bytes: int | NotGiven | None = NOT_GIVEN
    resume_session: bool | str = False
    agent_provider: AgentProvider | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT
    timeout_seconds: int | None = 600
    origin: str | None = None


async def draw_svg_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    canvas: tuple[int, int] | NotGiven = NOT_GIVEN,
    max_bytes: int | NotGiven | None = NOT_GIVEN,
    resume_session: bool | str = False,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int | None = 600,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> SvgRun:
    """Start drawing the SVG named `name`, or changing it when it exists, and return its run once the agent works."""
    request = validated(
        SvgImageRequest,
        prompt=prompt,
        name=name,
        directory=directory,
        data_directory=data_directory,
        references=references or [],
        marks=marks or [],
        canvas=canvas,
        max_bytes=max_bytes,
        resume_session=resume_session,
        agent_provider=agent_provider,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        origin=origin,
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
    return await detaching.detach(BACKGROUND_COMMAND, absolute, root, data, SvgDetachedRun)


async def start(request: SvgImageRequest, intelligence: Intelligence | None = None) -> SvgInProcessRun:
    """Check the request, set up the work folder, and start the agent that draws in it."""
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    name = image_name(request.name, root, data)
    sent = references(request.references)
    marking.require_marks(request.marks)
    run_id = new_run_id()
    with claimed(root, data, name, run_id) as (image, lock):
        resumed = sessions.resumed(image.runs, request.resume_session, image.name)
        provider = sessions.provider(request.agent_provider, resumed, image.name)
        if intelligence is None:
            provider = resolve_agent_provider(provider)
        intelligence, model = select_intelligence(intelligence, provider, request.model, DEFAULT_INTELLIGENCE_MODELS)
        if not image.path.is_file() and request.marks:
            raise invalid(
                f"There is no image named {image.name} to edit, so marks cannot be used. Leave them out to draw the "
                "image, or name an image that exists.",
                image.name,
            )
        budgets = _budgets(request, image)
        folder = image.run_folder(run_id)
        work = image.folder / WORK
        images, prompt = _prepare(request, sent, image, resumed, budgets, folder / INPUTS, work)
        agent = await intelligence.start(
            AgentRequest(
                prompt=prompt,
                model=model,
                images=images,
                workspace=HostWorkspace(path=work),
                writable=True,
                reasoning_effort=request.reasoning_effort,
                timeout_seconds=(
                    None if request.timeout_seconds is None else request.timeout_seconds + AGENT_GRACE_SECONDS
                ),
                resume=resumed.session_id if resumed is not None else None,
                session_directory=image.folder / SESSIONS,
                follow_up=Checking(work).follow_up,
            )
        )
        try:
            run = ImageRunRecord(
                id=run_id,
                method="svg",
                prompt=request.prompt,
                request={
                    "model": model,
                    "reasoning_effort": request.reasoning_effort,
                    **budgets.model_dump(mode="json"),
                    "images": [path.relative_to(folder).as_posix() for path in images],
                    "marks": [mark.model_dump(mode="json") for mark in request.marks],
                    "resumed": resumed.session_id if resumed is not None else None,
                },
                origin=request.origin,
                agent_provider=provider,
                session_id=agent.session_id,
                pid=os.getpid(),
                started=datetime.now(UTC),
            )
            image.runs.append(run)
            image.save_runs()
            work_done = partial(_follow, agent, intelligence.steering, image, run, budgets)
            return SvgInProcessRun(
                image,
                run,
                work_done,
                request.timeout_seconds,
                lock,
                SVG_SUFFIX,
                stop=agent.cancel,
                preview_suffix=".png",
            )
        except BaseException:
            await agent.cancel()
            raise


class Checking:
    """The build the agent is handed once, when it finishes a turn without having built image.py as it is."""

    def __init__(self, work: Path) -> None:
        self._work = work
        self._asked = False

    async def follow_up(self) -> str | None:
        if self._asked or await asyncio.to_thread(build.built, self._work):
            return None
        self._asked = True
        try:
            check = await asyncio.to_thread(build.build, self._work)
        except ImageDesignError as error:
            return prompting.checked(f"The build failed. {error}")
        return prompting.checked(check.describe())


def _prepare(
    request: SvgImageRequest,
    sent: list[Reference],
    image: StoredImage,
    resumed: ImageRunRecord | None,
    budgets: SvgBudgets,
    inputs: Path,
    work: Path,
) -> tuple[list[Path], str]:
    """Set up the work folder and write the images to show into `inputs`; return those images and the prompt.

    The work folder holds the image as it is, unless the request resumes the session of the image's last run and that
    run did not finish, when it is kept as that run left it.
    """
    last = image.runs[-1] if image.runs else None
    kept = resumed is not None and resumed is last and resumed.status != "done" and (work / SCRIPT).is_file()
    if not kept:
        _reset(work, image)
    build.write_drawing(work, build.Drawing(name=image.name, budgets=budgets))
    inputs.mkdir(parents=True, exist_ok=True)
    shown: list[Path] = []
    existing = ""
    marks_block = ""
    if image.path.is_file():
        content = image.path.read_bytes()
        rendered = write(inputs / CURRENT_PNG, pictures.svg_png(content, image.path.parent))
        copied = write(inputs / CURRENT_SVG, content)
        if not kept:
            shown.append(rendered)
            existing = _existing(image, rendered, copied)
        if request.marks:
            marked = write(inputs / MARKED, marking.drawn(rendered.read_bytes(), request.marks))
            shown.append(marked)
            under = measure.parts_under(content, request.marks, image.path.parent)
            marks_block = prompting.marks(request.marks, marked, under)
    sent_paths = write_references(sent, inputs)
    shown.extend(sent_paths)
    references_block = prompting.references(sent_paths)
    if resumed is None:
        prompt = prompting.draw(
            request.prompt, work, budgets, build.command(work), existing, references_block, marks_block
        )
        return shown, prompt
    state = prompting.KEPT if kept else prompting.RESET + (existing or prompting.NEW)
    changed = budgets if budgets != _recorded_budgets(resumed) else None
    return shown, prompting.resume(request.prompt, state, changed, references_block, marks_block)


def _existing(image: StoredImage, rendered: Path, copied: Path) -> str:
    """What the agent is told of the drawing it changes, by whether image.py built the image's file."""
    if not (image.folder / SCRIPT).is_file():
        return prompting.UNSCRIPTED.format(svg=copied, current=rendered)
    current = image.version(image.versions.current) if image.versions.current is not None else None
    if current is None or current.method != "svg":
        return prompting.UNMATCHED.format(svg=copied, current=rendered)
    return prompting.EDIT.format(current=rendered)


def _reset(work: Path, image: StoredImage) -> None:
    """Make the work folder hold the image as it is: its image.py and lock, and its file as image.svg."""
    try:
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        script = image.folder / SCRIPT
        if script.is_file():
            shutil.copyfile(script, work / SCRIPT)
            if lock_path(script).is_file():
                shutil.copyfile(lock_path(script), lock_path(work / SCRIPT))
        if image.path.is_file():
            shutil.copyfile(image.path, work / build.SVG)
    except OSError as error:
        raise ImageDesignError(
            f"The work folder {work} could not be set up: {error}. Close what has its files open, and try again.",
            None,
            image.name,
        ) from None


def _budgets(request: SvgImageRequest, image: StoredImage) -> SvgBudgets:
    """The budgets given, with each left out kept from the image's last drawing.

    A new drawing's canvas is the default, and that of an SVG the tool did not draw is its own size.
    """
    kept = image.record.budgets
    canvas = request.canvas
    if isinstance(canvas, NotGiven):
        own = pictures.describe(image.path.read_bytes()) if image.path.is_file() else None
        canvas = kept.canvas if kept is not None else (own.width, own.height) if own is not None else DEFAULT_SVG_CANVAS
    limits: dict[str, int | None] = {}
    for field in BUDGETS:
        given = getattr(request, field)
        limits[field] = (getattr(kept, field) if kept is not None else None) if isinstance(given, NotGiven) else given
    return SvgBudgets(canvas=canvas, **limits)


def _recorded_budgets(run: ImageRunRecord) -> SvgBudgets | None:
    try:
        return SvgBudgets.model_validate({field: run.request.get(field) for field in ("canvas", *BUDGETS)})
    except ValueError:
        return None


async def _follow(
    agent: AgentRun,
    steering_mode: Steering,
    image: StoredImage,
    run: ImageRunRecord,
    budgets: SvgBudgets,
    output: RunOutput,
) -> None:
    """Report what the agent does and deliver steering while it works, then keep what image.py builds."""
    work = image.folder / WORK
    delivering = asyncio.create_task(_deliver(agent, steering_mode, image.run_folder(run.id), work, output))
    renders = Renders(work / build.RENDER)
    try:
        async for event in agent.events():
            if agent.session_id is not None:
                run.session_id = agent.session_id
            if event.kind == "terminal":
                continue
            output.event("agent", agent_events.shown(event), event.model_dump(mode="json"))
            if event.kind == "usage":
                output.used(agent_events.added(run.usage, event.data))
            elif event.kind == "tool_result" and (render := renders.new()) is not None:
                output.preview(render, renders.count - 1)
    finally:
        delivering.cancel()
        await asyncio.wait([delivering])
    ended = await agent.result()
    if ended.error is not None or ended.cancelled:
        stopped = ended.error or "it was stopped."
        raise ImageDesignError(
            f"The agent did not finish: {stopped} Its work is kept; go on with resume_session=True.", "agent-failed"
        )
    try:
        await asyncio.to_thread(build.build, work)
    except ImageDesignError as error:
        raise ImageDesignError(
            f"The drawing did not build as the agent finished. {error} Go on with resume_session=True to have the "
            "agent fix it.",
            "build-failed",
        ) from None
    output.image((work / build.SVG).read_bytes(), read_script(work / SCRIPT))
    image.record.budgets = budgets
    image.save_record()


async def _deliver(agent: AgentRun, steering_mode: Steering, run_folder: Path, work: Path, output: RunOutput) -> None:
    """Deliver each steering message left for the run, looking for them as often as for a cancel."""
    while True:
        for message in steering.pending(run_folder):
            await _deliver_one(agent, steering_mode, message, run_folder, work, output)
        await asyncio.sleep(image_runs.POLL_SECONDS)


async def _deliver_one(
    agent: AgentRun, steering_mode: Steering, message: Path, run_folder: Path, work: Path, output: RunOutput
) -> None:
    given = steering.read(message)
    folder = steering.delivered(message, run_folder)
    attached = [folder / name for name in given.references]
    marks_block = ""
    shown = list(attached)
    if given.marks:
        marked: Path | None = None
        under: list[list[tuple[str, float]]] = [[] for _ in given.marks]
        if (work / build.RENDER).is_file():
            marked = write(folder / MARKED, marking.drawn((work / build.RENDER).read_bytes(), given.marks))
            shown.insert(0, marked)
            with contextlib.suppress(ImageDesignError, OSError):
                content = (work / build.SVG).read_bytes()
                under = await asyncio.to_thread(measure.parts_under, content, given.marks, work)
        marks_block = prompting.marks(given.marks, marked, under)
    error: str | None = None
    try:
        await agent.steer(given.message + prompting.references(attached) + marks_block, shown)
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


class Renders:
    """Each new render.png the agent's builds make, told apart by when it was written and its size."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._seen = self._stamp()
        self.count = 0

    def new(self) -> bytes | None:
        stamp = self._stamp()
        if stamp is None or stamp == self._seen:
            return None
        self._seen = stamp
        try:
            content = self._path.read_bytes()
        except OSError:
            return None
        self.count += 1
        return content

    def _stamp(self) -> tuple[int, int] | None:
        try:
            stat = self._path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size


def _require_arguments(request: SvgImageRequest) -> None:
    """Raise for arguments the drawing cannot take, before anything is kept or started."""
    name = request.name
    if PurePosixPath(name.replace("\\", "/")).suffix.lower() != SVG_SUFFIX:
        raise invalid(
            f"{name!r} does not end in .svg, and draw_svg_image draws only SVGs. To redraw an image as an SVG, pass "
            "it in references and name a new .svg.",
            name,
        )
    if not request.prompt.strip():
        raise invalid("The prompt is empty. Say what to draw, or what to change.", name)
    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise invalid("timeout_seconds must be more than 0, or None for no limit.", name)
    if not isinstance(request.canvas, NotGiven) and min(request.canvas) < 1:
        width, height = request.canvas
        raise invalid(f"canvas is {width}x{height}. Its width and height must each be at least 1.", name)
    for field in BUDGETS:
        given = getattr(request, field)
        if isinstance(given, int) and given < 1:
            raise invalid(f"{field} is {given}. Pass at least 1, or None for no limit.", name)
