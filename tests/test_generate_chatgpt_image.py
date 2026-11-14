"""Creating and editing images with the image generation in Codex, with the Codex agent faked, from the library and CLI."""

import asyncio
from collections.abc import AsyncIterator, Callable
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any

from fake_openai import picture
from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.chatgpt_image import generate
from image_design.capabilities.chatgpt_image.generate import MARKS_NOTE
from image_design.cli import app
from image_design.intelligence.events import EventLog
from image_design.intelligence.schemas import AgentEvent, AgentEventKind, AgentRequest, AgentResult, Steering
from image_design.schemas import (
    DEFAULT_INTELLIGENCE_MODELS,
    ImageDesignError,
    ImageEvent,
    ImageRequestImage,
    ImageResult,
    Mark,
)
from image_design.shared.images import runs
from image_design.shared.images.store import LOCKS

runner = CliRunner()
CACTUS = Mark(shape="circle", points=[(0.2, 0.2), (0.8, 0.8)], note="this pot")
SWATCH = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30"/></svg>'
IMAGES = Path(".image-design/.agents/images")


class FakeAgentRun:
    """An agent that does what its behavior says, and records being stopped."""

    def __init__(self, request: AgentRequest, behavior: Callable[["FakeAgentRun"], None]) -> None:
        self.request = request
        self.cancels = 0
        self._log = EventLog()
        self._ended: asyncio.Future[AgentResult] = asyncio.get_running_loop().create_future()
        behavior(self)

    @property
    def session_id(self) -> str | None:
        return "fake-session"

    def events(self) -> AsyncIterator[AgentEvent]:
        return self._log.replay()

    async def steer(self, message: str, images: list[Path] | None = None) -> None:
        raise NotImplementedError

    async def cancel(self) -> None:
        self.cancels += 1
        # Stopping a real agent takes a while, during which readers of the run's events wait.
        await asyncio.sleep(0.05)
        self.end(AgentResult(cancelled=True))

    async def result(self) -> AgentResult:
        return await self._ended

    def emit(self, kind: AgentEventKind, **data: Any) -> None:
        self._log.emit(AgentEvent(kind=kind, data=data))

    def end(self, result: AgentResult) -> None:
        if not self._ended.done():
            self._ended.set_result(result)
            self.emit("terminal", **result.model_dump(mode="json"))


def makes(color: str) -> Callable[[FakeAgentRun], None]:
    """An agent that makes one image of `color` and keeps going, as the real one would, until it is stopped."""

    def behave(run: FakeAgentRun) -> None:
        assert run.request.generated_images is not None
        run.request.generated_images.mkdir(parents=True)
        path = run.request.generated_images / "ig_1.png"
        path.write_bytes(picture(256, 256, color))
        run.emit("tool_result", tool_name="imageGeneration", success=True)
        run.emit("image", path=str(path), prompt="The prompt as sent.")

    return behave


def fails(error: str) -> Callable[[FakeAgentRun], None]:
    def behave(run: FakeAgentRun) -> None:
        run.emit("tool_result", tool_name="imageGeneration", success=False, error=error)
        run.end(AgentResult(text="The image tool failed."))

    return behave


def says(text: str) -> Callable[[FakeAgentRun], None]:
    return lambda run: run.end(AgentResult(text=text))


def hangs(run: FakeAgentRun) -> None:
    pass


class FakeImageAgent:
    """Stands in for Codex, recording each agent it starts."""

    implementation = "fake"
    steering: Steering = "queued"

    def __init__(self) -> None:
        self.behavior: Callable[[FakeAgentRun], None] = makes("#3a86ff")
        self.refusal: str | None = None
        self.runs: list[FakeAgentRun] = []

    def preflight(self) -> None:
        pass

    async def start(self, request: AgentRequest) -> FakeAgentRun:
        if self.refusal is not None:
            raise ImageDesignError(self.refusal, "not-set-up")
        run = FakeAgentRun(request, self.behavior)
        self.runs.append(run)
        return run


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> FakeImageAgent:
    """The Codex agent faked, also for the CLI, in a working directory of its own."""
    fake = FakeImageAgent()
    monkeypatch.setattr(
        generate,
        "select_intelligence",
        lambda intelligence, *_: (intelligence or fake, DEFAULT_INTELLIGENCE_MODELS["codex"]),
    )
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.01)
    monkeypatch.chdir(tmp_path_factory.mktemp("work"))
    return fake


async def made(agent: FakeImageAgent, **arguments: Any) -> ImageResult:
    run = await lib.generate_chatgpt_image(intelligence=agent, **arguments)
    assert [event.kind async for event in run.events()] == ["started", "version", "finished"]
    return await run.result()


def colors(content: bytes) -> set[tuple[int, ...]]:
    with Image.open(BytesIO(content)) as image:
        counted = image.convert("RGB").getcolors(maxcolors=1 << 16) or []
    return {color for _, color in counted if isinstance(color, tuple)}


def sent_paths(request: AgentRequest) -> list[Path]:
    found = re.search(r"referenced_image_paths: (.*)", request.prompt)
    assert found is not None
    return [Path(path) for path in json.loads(found.group(1))]


async def test_an_image_is_created_then_edited_with_marks_and_a_reference_and_each_agent_stops_after_its_image(
    agent: FakeImageAgent,
) -> None:
    created = await made(agent, prompt="A paper-cut cactus.", name="cactus.png", transparent=True)
    Path("palette.svg").write_text(SWATCH, encoding="utf-8")
    agent.behavior = makes("#e63946")
    edited = await made(
        agent, prompt="Make the pot blue.", name="cactus.png", references=[Path("palette.svg")], marks=[CACTUS]
    )

    creating, editing = agent.runs
    assert creating.request.model == DEFAULT_INTELLIGENCE_MODELS["codex"]
    assert creating.request.reasoning_effort == "low"
    assert (creating.request.workspace, creating.request.images) == (None, [])
    assert "-----\nA paper-cut cactus.\n-----" in creating.request.prompt
    assert "transparent_background: true" in creating.request.prompt
    assert sent_paths(creating.request) == []
    assert (created.status, created.usage) == ("done", None)
    assert [(version.id, version.method) for version in created.versions] == [("v1", "chatgpt")]
    image, marked, palette = sent_paths(editing.request)
    assert [path.name for path in (image, marked, palette)] == ["image.png", "marked.png", "reference-1.png"]
    assert colors(image.read_bytes()) == {(58, 134, 255)}
    assert colors(marked.read_bytes()) == {(58, 134, 255), (255, 0, 0)}
    assert Image.open(palette).size == (40, 30)
    assert "transparent_background: false" in editing.request.prompt
    assert f"Make the pot blue.\n\n{MARKS_NOTE}\n- Mark 1 is a red circle: this pot" in editing.request.prompt
    assert [version.id for version in edited.versions] == ["v2"]
    assert colors(edited.path.read_bytes()) == {(230, 57, 70)}
    assert [run.cancels for run in agent.runs] == [1, 1]
    [folder] = IMAGES.iterdir()
    record = json.loads((folder / "runs.json").read_text(encoding="utf-8"))["runs"][-1]
    assert record["image_prompt"] == "The prompt as sent."
    assert record["request"]["codex_model"] == DEFAULT_INTELLIGENCE_MODELS["codex"]
    assert record["request"]["images"] == ["inputs/image.png", "inputs/marked.png", "inputs/reference-1.png"]
    assert not list(folder.glob("runs/*/made/*"))


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"name": "cactus.jpg"}, "only PNG images"),
        ({"prompt": " "}, "The prompt is empty"),
        ({"references": [Path("palette.png")] * 6}, "at most 5 images"),
        ({"marks": [CACTUS]}, "no image named cactus.png to edit"),
        ({"references": [Path("broken.svg")]}, "is an SVG that could not be rendered"),
        ({"references": [Path("notes.txt")]}, "is not an image the tool can read"),
        ({"reasoning_effort": "extreme"}, "reasoning_effort"),
        ({"detach": True}, "cannot be used by a detached run"),
        ({"signed_in_with_an_api_key": True}, "signed in with an API key"),
    ],
)
async def test_a_request_codex_cannot_take_is_refused_before_anything_is_sent_or_kept(
    agent: FakeImageAgent, arguments: dict[str, Any], refusal: str
) -> None:
    Path("palette.png").write_bytes(picture(64, 64, "#000000"))
    Path("broken.svg").write_text("<svg", encoding="utf-8")
    Path("notes.txt").write_text("Not an image.", encoding="utf-8")
    if arguments.pop("signed_in_with_an_api_key", False):
        agent.refusal = "Codex is signed in with an API key. It makes images only with a ChatGPT sign-in."

    with pytest.raises(ImageDesignError, match=refusal):
        await lib.generate_chatgpt_image(
            prompt=arguments.pop("prompt", "A cactus."),
            name=arguments.pop("name", "cactus.png"),
            intelligence=agent,
            **arguments,
        )

    assert agent.runs == []
    assert not list(IMAGES.glob("*"))
    assert not list(Path(".image-design/.agents", LOCKS).glob("*"))


@pytest.mark.parametrize(
    ("behavior", "arguments", "status", "error"),
    [
        (fails("The ChatGPT plan's limit on making images (image_gen) is reached."), {}, "failed", "limit on making"),
        (says("I cannot make that."), {}, "failed", "without making an image. Codex said: I cannot make that."),
        (hangs, {"timeout_seconds": 1}, "timed-out", "did not finish within 1 seconds"),
        (hangs, {"cancel": True}, "cancelled", None),
    ],
)
async def test_a_run_that_makes_no_image_ends_saying_why_stops_its_agent_and_leaves_the_image_free(
    agent: FakeImageAgent,
    behavior: Callable[[FakeAgentRun], None],
    arguments: dict[str, Any],
    status: str,
    error: str | None,
) -> None:
    agent.behavior = behavior
    cancel = arguments.pop("cancel", False)

    run = await lib.generate_chatgpt_image("A cactus.", name="cactus.png", intelligence=agent, **arguments)
    if cancel:
        await run.cancel()
    result = await run.result()

    assert result.status == status
    if error is None:
        assert result.error is None
    else:
        assert result.error is not None
        assert error in result.error
    assert agent.runs[0].cancels == 1
    assert not result.path.exists()
    agent.behavior = makes("#3a86ff")
    assert (await made(agent, prompt="A cactus.", name="cactus.png")).status == "done"


async def test_a_request_preview_is_what_the_agent_is_then_asked_and_starts_no_agent(
    agent: FakeImageAgent,
) -> None:
    Path("palette.svg").write_text(SWATCH, encoding="utf-8")
    edit: dict[str, Any] = {"prompt": "Make the pot blue.", "name": "cactus.png", "references": [Path("palette.svg")]}
    creating = lib.preview_chatgpt_image_request("A paper-cut cactus.", name="cactus.png", transparent=True)
    with pytest.raises(ImageDesignError, match="only PNG images"):
        lib.preview_chatgpt_image_request("A cactus.", name="cactus.jpg")
    started = len(agent.runs)
    await made(agent, prompt="A paper-cut cactus.", name="cactus.png", transparent=True)
    editing = lib.preview_chatgpt_image_request(marks=[CACTUS], reasoning_effort="medium", **edit)
    await made(agent, marks=[CACTUS], reasoning_effort="medium", **edit)

    asked = agent.runs[-1].request
    assert (started, len(agent.runs)) == (0, 2)
    assert (creating.method, creating.edits, creating.images) == ("chatgpt", False, [])
    assert (creating.prompt, creating.added) == ("A paper-cut cactus.", None)
    assert creating.parameters == {
        "transparent_background": True,
        "codex_model": DEFAULT_INTELLIGENCE_MODELS["codex"],
        "reasoning_effort": "low",
    }
    # The images are in the order the image tool gets them: the image, its marked copy, then the references.
    assert editing.images == [
        ImageRequestImage(role="source", path=Path(".image-design/cactus.png").resolve()),
        ImageRequestImage(role="marked-copy", path=None),
        ImageRequestImage(role="reference", path=Path("palette.svg")),
    ]
    assert len(sent_paths(asked)) == len(editing.images)
    assert f"-----\n{editing.prompt}\n-----" in asked.prompt
    assert editing.added == f"{MARKS_NOTE}\n- Mark 1 is a red circle: this pot"
    assert editing.parameters == {
        "transparent_background": False,
        "codex_model": asked.model,
        "reasoning_effort": asked.reasoning_effort,
    }


def test_the_cli_prints_the_image_made_and_exits_with_the_run_s_status(agent: FakeImageAgent) -> None:
    made = runner.invoke(app, ["generate-chatgpt-image", "A cactus.", "--name", "cactus.png", "--transparent"])
    agent.behavior = says("I cannot make that.")
    failed = runner.invoke(app, ["generate-chatgpt-image", "A pot.", "--name", "cactus.png", "--json"])

    assert made.exit_code == 0, made.output
    assert made.stdout.splitlines() == [str(Path(".image-design", "cactus.png"))]
    assert "Making cactus.png with chatgpt." in made.stderr
    assert "transparent_background: true" in agent.runs[0].request.prompt
    assert failed.exit_code == 1
    events = [ImageEvent.model_validate_json(line) for line in failed.stdout.splitlines()]
    assert [event.kind for event in events] == ["started", "failed"]
    assert "I cannot make that." in events[-1].text
