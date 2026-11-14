"""Drawing SVG images with the agent faked and image.py run in this process, from the library and the CLI."""

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from io import BytesIO
import json
from pathlib import Path
import runpy
from typing import Any
import uuid

from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.svg_image import build, draw, prompting
from image_design.cli import app
from image_design.intelligence.events import EventLog
from image_design.intelligence.schemas import AgentEvent, AgentEventKind, AgentRequest, AgentResult, Steering
from image_design.schemas import ImageDesignError, ImageEvent, ImageResult, Mark, SvgBudgets
from image_design.shared.images import runs
from image_design.shared.images.store import LOCKS, SCRIPT, lock_path

runner = CliRunner()
IMAGES = Path(".image-design/.agents/images")
SAIL = Mark(shape="circle", points=[(0.45, 0.05), (0.8, 0.55)], note="this sail")
SWATCH = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30" fill="#457b9d"/></svg>'
)
BROKEN = 'raise RuntimeError("The sail is missing.")\n'


def sailboat(sail: str = "#e63946") -> str:
    """An image.py that draws a sailboat of three named parts, as an agent would write it."""
    return f"""# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
from pathlib import Path

SAIL = "{sail}"
Path(__file__).with_name("image.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="48" viewBox="0 0 64 48">'
    '<g id="sea"><rect y="32" width="64" height="16" fill="#1d3557"/></g>'
    '<g id="boat"><rect x="16" y="26" width="32" height="6" fill="#8d5524"/>'
    '<g id="sail"><polygon points="32,4 32,26 50,26" fill="' + SAIL + '"/></g></g></svg>',
    encoding="utf-8",
)
"""


class FakeAgentRun:
    """An agent that draws in its workspace as its behavior says, and records what it was sent."""

    def __init__(self, request: AgentRequest, behavior: "Behavior") -> None:
        self.request = request
        self.cancels = 0
        self.steered: list[tuple[str, list[Path]]] = []
        self.follow_ups: list[str] = []
        self._session = request.resume or f"session-{uuid.uuid4().hex[:6]}"
        self._messages: asyncio.Queue[str] = asyncio.Queue()
        self._log = EventLog()
        self._ended: asyncio.Future[AgentResult] = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(behavior(self))
        self._task.add_done_callback(self._raised)

    def _raised(self, task: asyncio.Task[None]) -> None:
        """End the run with what a behavior raised, so a test shows it rather than waiting out the run."""
        if not task.cancelled() and (error := task.exception()) is not None:
            self.end(AgentResult(error=f"The fake agent raised {error!r}", session_id=self._session))

    @property
    def session_id(self) -> str | None:
        return self._session

    @property
    def work(self) -> Path:
        assert self.request.workspace is not None
        return self.request.workspace.path

    def events(self) -> AsyncIterator[AgentEvent]:
        return self._log.replay()

    async def steer(self, message: str, images: list[Path] | None = None) -> None:
        if self._ended.done():
            raise ImageDesignError("The agent run has ended, so the steering message was not delivered.")
        self.steered.append((message, list(images or [])))
        self._messages.put_nowait(message)

    async def cancel(self) -> None:
        self.cancels += 1
        self._task.cancel()
        await asyncio.wait([self._task])
        self.end(AgentResult(cancelled=True, session_id=self._session))

    async def result(self) -> AgentResult:
        return await self._ended

    def emit(self, kind: AgentEventKind, text: str = "", **data: Any) -> None:
        self._log.emit(AgentEvent(kind=kind, text=text, data=data))

    def end(self, result: AgentResult) -> None:
        if not self._ended.done():
            self._ended.set_result(result)
            self._log.emit(AgentEvent(kind="terminal", text=result.error or result.text, data=result.model_dump()))

    def writes(self, script: str) -> None:
        self.emit("tool_call", "Write image.py", tool_name="Write", arguments={"file_path": "image.py"})
        (self.work / SCRIPT).write_text(script, encoding="utf-8")
        self.emit("tool_result", "", tool_name="Write", success=True)

    async def builds(self) -> None:
        command = build.command(self.work)
        self.emit("tool_call", f"Bash {command}", tool_name="Bash", arguments={"command": command})
        try:
            check = await asyncio.to_thread(build.build, self.work)
        except ImageDesignError as error:
            self.emit("tool_result", str(error), tool_name="Bash", success=False)
            return
        self.emit("tool_result", check.describe(), tool_name="Bash", success=True)

    async def message(self) -> str:
        return await self._messages.get()

    async def finishes(self, text: str = "I drew a sailboat.") -> None:
        """End the turn as an agent does: act on each follow-up the run gives, then answer."""
        while self.request.follow_up is not None and (follow_up := await self.request.follow_up()) is not None:
            self.follow_ups.append(follow_up)
            await self.builds()
        self.emit("message", text)
        self.emit("usage", model="fake", input_tokens=100, output_tokens=20, cost={"USD": 0.01})
        self.end(AgentResult(text=text, session_id=self._session))


Behavior = Callable[[FakeAgentRun], Coroutine[Any, Any, None]]


def draws(sail: str = "#e63946", finding: str | None = None) -> Behavior:
    """An agent that writes the sailboat, builds it, and finishes; first checking image.py holds `finding`, if given."""

    async def behave(run: FakeAgentRun) -> None:
        if finding is not None:
            assert (run.work / SCRIPT).read_text(encoding="utf-8") == finding
        run.writes(sailboat(sail))
        await run.builds()
        await run.finishes()

    return behave


def writes_only(script: str) -> Behavior:
    """An agent that writes image.py and finishes without building it."""

    async def behave(run: FakeAgentRun) -> None:
        run.writes(script)
        await run.finishes()

    return behave


def stops(error: str) -> Behavior:
    """An agent that writes and builds a drawing, then stops with an error before it finishes."""

    async def behave(run: FakeAgentRun) -> None:
        run.writes(sailboat("#2a9d8f"))
        await run.builds()
        run.end(AgentResult(error=error, session_id=run.session_id))

    return behave


def steered_to(sail: str) -> Behavior:
    """An agent that draws, waits for a steering message, then redraws the sail."""

    async def behave(run: FakeAgentRun) -> None:
        run.writes(sailboat())
        await run.builds()
        await run.message()
        run.writes(sailboat(sail))
        await run.builds()
        await run.finishes()

    return behave


async def hangs(run: FakeAgentRun) -> None:
    await asyncio.Event().wait()


class FakeDrawingAgent:
    """Stands in for an agent provider, recording each agent it starts."""

    implementation = "fake"
    steering: Steering = "queued"

    def __init__(self) -> None:
        self.behavior: Behavior = draws()
        self.runs: list[FakeAgentRun] = []

    def preflight(self) -> None:
        pass

    async def start(self, request: AgentRequest) -> FakeAgentRun:
        run = FakeAgentRun(request, self.behavior)
        self.runs.append(run)
        return run


def run_in_process(work: Path) -> None:
    """image.py run in this process, as `uv run --script` runs it, so the tests start no process."""
    lock = lock_path(work / SCRIPT)
    if not lock.is_file():
        lock.write_text("version = 1\n", encoding="utf-8")
    try:
        runpy.run_path(str(work / SCRIPT), run_name="__main__")
    except Exception as error:
        raise ImageDesignError(
            f"`uv run --script image.py` failed with exit code 1:\n{type(error).__name__}: {error}", "build-failed"
        ) from None


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> FakeDrawingAgent:
    """The agent provider faked, also for the CLI, in a working directory of its own."""
    fake = FakeDrawingAgent()
    monkeypatch.setattr(draw, "resolve_agent_provider", lambda provider: provider or "codex")
    monkeypatch.setattr(draw, "select_intelligence", lambda intelligence, *_: (intelligence or fake, "fake-model"))
    monkeypatch.setattr(build, "run_script", run_in_process)
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.01)
    monkeypatch.chdir(tmp_path_factory.mktemp("work"))
    return fake


async def drawn(agent: FakeDrawingAgent, **arguments: Any) -> tuple[ImageResult, list[ImageEvent]]:
    arguments.setdefault("prompt", "A sailboat.")
    arguments.setdefault("name", "sailboat.svg")
    run = await lib.draw_svg_image(intelligence=agent, **arguments)
    events = [event async for event in run.events()]
    return await run.result(), events


def folder() -> Path:
    [only] = IMAGES.iterdir()
    return only.resolve()


def runs_kept() -> list[dict[str, Any]]:
    return json.loads((folder() / "runs.json").read_text(encoding="utf-8"))["runs"]


async def test_a_drawing_is_created_then_edited_with_marks_and_a_reference_each_version_kept_with_its_script(
    agent: FakeDrawingAgent,
) -> None:
    created, events = await drawn(agent)
    Path("palette.svg").write_text(SWATCH, encoding="utf-8")
    agent.behavior = draws("#457b9d", finding=sailboat())
    edited, _ = await drawn(agent, prompt="Make the sail blue.", references=[Path("palette.svg")], marks=[SAIL])

    work = folder() / "work"
    creating, editing = agent.runs
    assert creating.request.workspace is not None
    assert (creating.request.workspace.path, creating.request.writable) == (work, True)
    assert (creating.request.images, creating.request.resume) == ([], None)
    assert creating.request.session_directory == folder() / "sessions"
    assert build.command(work) in creating.request.prompt
    assert "<request>\nA sailboat.\n</request>" in creating.request.prompt
    assert "A canvas of 512 by 512" in creating.request.prompt
    kinds = [event.kind for event in events]
    assert kinds[0] == "started"
    assert kinds[-2:] == ["version", "finished"]
    assert {"agent", "preview"} <= set(kinds)
    assert "Making sailboat.svg with fake-model." in events[0].text
    assert events[0].data["prompt"] == "A sailboat."
    assert (created.status, [(version.id, version.method) for version in created.versions]) == ("done", [("v1", "svg")])
    assert created.usage is not None
    assert (created.usage.output_tokens, created.usage.cost) == (20, 0.01)
    current, marked, palette = editing.request.images
    assert [path.name for path in (current, marked, palette)] == ["current.png", "marked.png", "reference-1.png"]
    assert Image.open(palette).size == (40, 30)
    prompt = editing.request.prompt
    assert "Read image.py first and change it rather than starting over." in prompt
    assert "- Mark 1 is a red circle: this sail. Under it: boat (" in prompt
    assert "), boat/sail (" in prompt
    assert f"References for this request (also attached):\n- {palette}" in prompt
    assert [version.id for version in edited.versions] == ["v2"]
    assert "#457b9d" in edited.path.read_text(encoding="utf-8")
    assert (folder() / SCRIPT).read_text(encoding="utf-8") == sailboat("#457b9d")
    assert lock_path(folder() / SCRIPT).is_file()
    [first, second] = (version for version in lib.restore_image_version("sailboat.svg", "v1").versions)
    assert first.script is not None
    assert second.script is not None
    assert (first.script.name, lock_path(first.script).is_file()) == ("v1.py", True)
    assert (folder() / SCRIPT).read_text(encoding="utf-8") == sailboat()
    assert "#e63946" in created.path.read_text(encoding="utf-8")
    record = json.loads((folder() / "image.json").read_text(encoding="utf-8"))
    assert record["budgets"] == {"canvas": [512, 512]}


async def test_budgets_are_told_the_agent_kept_on_an_edit_and_cleared_with_none(agent: FakeDrawingAgent) -> None:
    await drawn(agent, canvas=(64, 48), max_shapes=10, max_colors=3)
    agent.behavior = draws("#457b9d")
    await drawn(agent, prompt="Make the sail blue.", max_colors=None)

    creating, editing = agent.runs
    assert "A canvas of 64 by 48" in creating.request.prompt
    assert "At most 10 shapes" in creating.request.prompt
    assert "At most 3 colors" in creating.request.prompt
    assert "At most 10 shapes" in editing.request.prompt
    assert "colors:" not in editing.request.prompt
    check = lib.check_svg_image("sailboat.svg")
    assert (check.budgets.canvas, check.budgets.max_shapes, check.budgets.max_colors) == ((64, 48), 10, None)
    assert (check.shapes, check.colors) == (3, ["#1d3557", "#457b9d", "#8d5524"])
    assert [(part.id, part.shapes) for part in check.parts] == [("sea", 1), ("boat", 2), ("boat/sail", 1)]
    assert check.describe().splitlines()[1] == "Shapes: 3 (at most 10)."


async def test_a_resumed_session_goes_on_from_an_unfinished_run_s_work_and_keeps_its_agent_provider(
    agent: FakeDrawingAgent,
) -> None:
    agent.behavior = stops("The model is overloaded.")
    stopped, _ = await drawn(agent, agent_provider="claude")
    agent.behavior = draws("#e9c46a", finding=sailboat("#2a9d8f"))
    resumed, _ = await drawn(agent, prompt="Go on.", resume_session=True)
    agent.behavior = draws("#e63946", finding=sailboat("#e9c46a"))
    again, _ = await drawn(agent, prompt="Make the sail red.", resume_session=agent.runs[0].session_id)

    assert stopped.status == "failed"
    assert stopped.error is not None
    assert "The model is overloaded. Its work is kept; go on with resume_session=True." in stopped.error
    first, second, third = agent.runs
    assert second.request.resume == third.request.resume == first.session_id
    assert prompting.KEPT in second.request.prompt
    assert prompting.RESET in third.request.prompt
    assert (resumed.status, again.status) == ("done", "done")
    assert [run["agent_provider"] for run in runs_kept()] == ["claude", "claude", "claude"]
    with pytest.raises(ImageDesignError, match="goes on only on the one it started on"):
        await drawn(agent, resume_session=True, agent_provider="codex")
    with pytest.raises(
        ImageDesignError, match=f"has no session 'nope'. Its sessions, latest first: {first.session_id}"
    ):
        await drawn(agent, resume_session="nope")


async def test_steering_reaches_the_agent_with_references_and_marks_on_its_latest_render(
    agent: FakeDrawingAgent,
) -> None:
    agent.behavior = steered_to("#457b9d")
    Path("palette.svg").write_text(SWATCH, encoding="utf-8")

    run = await lib.draw_svg_image("A sailboat.", name="sailboat.svg", intelligence=agent)
    async for event in run.events():
        if event.kind == "preview":
            break
    lib.steer_svg_image("sailboat.svg", "Make the sail blue.", references=[Path("palette.svg")], marks=[SAIL])
    result = await run.result()
    events = [event async for event in run.events()]

    assert result.status == "done"
    [(message, images)] = agent.runs[0].steered
    assert [image.name for image in images] == ["marked.png", "reference-1.png"]
    assert message.startswith("Make the sail blue.\nReferences for this request (also attached):")
    assert "- Mark 1 is a red circle: this sail. Under it: boat (" in message
    [steered] = [event for event in events if event.kind == "steered"]
    assert (steered.text, steered.data["error"], steered.data["steering"]) == (
        "Steered: Make the sail blue.",
        None,
        "queued",
    )
    assert run.session_id == agent.runs[0].session_id
    with pytest.raises(ImageDesignError, match="has no drawing going"):
        lib.steer_svg_image("sailboat.svg", "Too late.")
    with pytest.raises(ImageDesignError, match="has ended"):
        await run.steer("Too late.")


async def test_an_agent_that_finishes_without_building_is_handed_the_build_once(agent: FakeDrawingAgent) -> None:
    agent.behavior = writes_only(sailboat())
    built, _ = await drawn(agent)
    agent.behavior = writes_only(BROKEN)
    broken, _ = await drawn(agent, prompt="Change it.")

    [checked] = agent.runs[0].follow_ups
    assert checked.startswith("The tool built image.py as you were finishing")
    assert "Named parts:\n- sea (1 shape)" in checked
    assert built.status == "done"
    [failed] = agent.runs[1].follow_ups
    assert "The build failed." in failed
    assert "RuntimeError: The sail is missing." in failed
    assert broken.status == "failed"
    assert broken.error is not None
    assert "did not build as the agent finished" in broken.error
    assert (folder() / SCRIPT).read_text(encoding="utf-8") == sailboat()


@pytest.mark.parametrize(
    ("behavior", "arguments", "status", "error"),
    [
        (stops("The model is overloaded."), {}, "failed", "The agent did not finish: The model is overloaded."),
        (hangs, {"timeout_seconds": 1}, "timed-out", "did not finish within 1 seconds"),
        (hangs, {"cancel": True}, "cancelled", None),
    ],
)
async def test_a_drawing_that_does_not_finish_ends_saying_why_stops_its_agent_and_leaves_the_image_free(
    agent: FakeDrawingAgent, behavior: Behavior, arguments: dict[str, Any], status: str, error: str | None
) -> None:
    agent.behavior = behavior
    cancel = arguments.pop("cancel", False)

    run = await lib.draw_svg_image("A sailboat.", name="sailboat.svg", intelligence=agent, **arguments)
    if cancel:
        await run.cancel()
    result = await run.result()

    assert result.status == status
    assert result.error == error or (error is not None and result.error is not None and error in result.error)
    assert agent.runs[0].cancels == 1
    assert not result.path.exists()
    agent.behavior = draws()
    assert (await drawn(agent))[0].status == "done"


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"name": "sailboat.png"}, "does not end in .svg"),
        ({"prompt": " "}, "The prompt is empty"),
        ({"canvas": (0, 10)}, "canvas is 0x10"),
        ({"max_shapes": 0}, "max_shapes is 0"),
        ({"marks": [SAIL]}, "no image named sailboat.svg to edit"),
        ({"resume_session": True}, "no agent session to resume"),
        ({"references": [Path("notes.txt")]}, "is not an image the tool can read"),
        ({"detach": True}, "cannot be used by a detached run"),
    ],
)
async def test_a_request_the_drawing_cannot_take_is_refused_before_anything_starts_or_is_kept(
    agent: FakeDrawingAgent, arguments: dict[str, Any], refusal: str
) -> None:
    Path("notes.txt").write_text("Not an image.", encoding="utf-8")

    with pytest.raises(ImageDesignError, match=refusal):
        await drawn(agent, **arguments)

    assert agent.runs == []
    assert not list(IMAGES.glob("*"))
    assert not list(Path(".image-design/.agents", LOCKS).glob("*"))


async def test_check_lists_what_resvg_skips_and_export_renders_each_format(agent: FakeDrawingAgent) -> None:
    Path(".image-design").mkdir()
    Path(".image-design/logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><script>go()</script>'
        '<rect width="40" height="20" fill="#ff000080"><animate attributeName="x" to="5"/></rect>'
        '<text x="2" y="12" direction="rtl">Hi</text></svg>',
        encoding="utf-8",
    )
    await drawn(agent)

    check = lib.check_svg_image("logo.svg")
    written = [
        lib.export_svg_image("sailboat.svg", Path(f"exports/sailboat.{suffix}"), scale=2) for suffix in ("png", "jpg")
    ]
    earlier = lib.export_svg_image("sailboat.svg", Path("exports/v1.webp"), version="v1")

    assert check.budgets.canvas == (40, 20)
    assert (check.shapes, check.texts, check.colors) == (2, 1, ["#ff000080"])
    assert check.skipped == ["<animate> (1)", "<script> (1)", "the direction attribute (1)"]
    assert "Text elements: 1." in check.describe()
    assert [Image.open(path).size for path in (*written, earlier)] == [(128, 96), (128, 96), (64, 48)]
    assert Image.open(written[1]).mode == "RGB"
    with pytest.raises(ImageDesignError, match="does not end in a format to export to"):
        lib.export_svg_image("sailboat.svg", Path("exports/sailboat.gif"))
    with pytest.raises(ImageDesignError, match="is not an SVG"):
        lib.check_svg_image("cactus.png")


async def test_activity_reads_each_run_s_events_and_then_only_what_came_since(agent: FakeDrawingAgent) -> None:
    await drawn(agent)
    activity = lib.read_image_activity("sailboat.svg")
    nothing_new = lib.read_image_activity("sailboat.svg", after=activity.cursor)
    await drawn(agent, prompt="Make the sail blue.")
    since = lib.read_image_activity("sailboat.svg", after=activity.cursor)

    assert activity.status == "done"
    assert activity.events[0].kind == "started"
    assert activity.events[-1].kind == "finished"
    assert nothing_new.events == []
    assert nothing_new.cursor == activity.cursor
    assert [event.data["prompt"] for event in since.events if event.kind == "started"] == ["Make the sail blue."]
    with pytest.raises(ImageDesignError, match="is not a cursor"):
        lib.read_image_activity("sailboat.svg", after="elsewhere:12")


def test_the_cli_draws_checks_exports_and_reads_activity(agent: FakeDrawingAgent) -> None:
    made = runner.invoke(
        app, ["draw-svg-image", "A sailboat.", "--name", "sailboat.svg", "--canvas", "64x48", "--max-colors", "none"]
    )
    checked = runner.invoke(app, ["check-svg-image", "--name", "sailboat.svg"])
    exported = runner.invoke(app, ["export-svg-image", "--name", "sailboat.svg", "--output", "out/boat.png"])
    activity = runner.invoke(app, ["read-image-activity", "--name", "sailboat.svg"])
    steered = runner.invoke(app, ["steer-svg-image", "--name", "sailboat.svg", "--message", "Too late."])
    bad = runner.invoke(app, ["draw-svg-image", "A boat.", "--name", "boat.svg", "--max-shapes", "lots"])

    assert made.exit_code == 0, made.output
    assert made.stdout.splitlines() == [str(Path(".image-design", "sailboat.svg"))]
    assert "Making sailboat.svg with fake-model." in made.stderr
    assert "I drew a sailboat." in made.stderr
    assert "A canvas of 64 by 48" in agent.runs[0].request.prompt
    assert checked.stdout.startswith("Canvas: 64x48.")
    assert exported.stdout.strip() == str(Path("out", "boat.png"))
    assert activity.stdout.splitlines()[-1].startswith("Status: done. To read only what comes next, pass --after ")
    assert isinstance(steered.exception, ImageDesignError)
    assert "has no drawing going" in str(steered.exception)
    assert bad.exit_code == 2


@pytest.mark.uv
def test_a_drawing_s_script_runs_with_uv_locked_and_rendered(tmp_path: Path) -> None:
    build.write_drawing(tmp_path, build.Drawing(name="sailboat.svg", budgets=SvgBudgets(canvas=(64, 48))))
    (tmp_path / SCRIPT).write_text(sailboat(), encoding="utf-8")

    check = build.build(tmp_path)

    assert lock_path(tmp_path / SCRIPT).is_file()
    assert (check.size, [part.id for part in check.parts]) == ((64.0, 48.0), ["sea", "boat", "boat/sail"])
    with Image.open(BytesIO((tmp_path / build.RENDER).read_bytes())) as render:
        assert render.size == (64, 48)
    assert build.built(tmp_path)
    (tmp_path / SCRIPT).write_text(BROKEN, encoding="utf-8")
    with pytest.raises(ImageDesignError, match=r"RuntimeError: The sail is missing."):
        build.build(tmp_path)
    assert not build.built(tmp_path)
